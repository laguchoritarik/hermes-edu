"""Reusable chat service that converges natural language to existing use cases."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import Protocol, cast

from hermes_edu.application.ports.chat import (
    ChatReferencePort,
    ChatSessionRepositoryPort,
    ChatTaskRunnerPort,
    ProjectContextPort,
)
from hermes_edu.application.services.chat_intent import ChatIntentParser
from hermes_edu.application.services.helper_agent import (
    apply_task_draft_patch,
    observation_from_tool,
    parsed_intent_from_decision,
    summarize_session,
)
from hermes_edu.application.services.tools import ToolCall, ToolRegistry, ToolRouter
from hermes_edu.application.use_cases.browser import BrowserService
from hermes_edu.domain.errors import HermesError, ValidationError
from hermes_edu.domain.models.agent import (
    AgentContext,
    AgentDecision,
    AgentDecisionType,
    AgentMetrics,
    AgentSkillSpec,
)
from hermes_edu.domain.models.chat import (
    ChatResponse,
    ChatRole,
    ChatSession,
    ChatStatus,
    ConversationTurn,
    ParsedIntent,
    ProjectContext,
    TaskDraft,
    utc_now,
)
from hermes_edu.domain.models.reference import SearchOutcome


class ConversationalAgent(Protocol):
    def decide(self, context: AgentContext) -> tuple[AgentDecision, AgentMetrics]: ...


class ChatService:
    """Stateful conversation facade over the existing Hermes application workflows."""

    def __init__(
        self,
        *,
        sessions: ChatSessionRepositoryPort,
        projects: ProjectContextPort,
        references: ChatReferencePort,
        runner: ChatTaskRunnerPort,
        parser: ChatIntentParser | None = None,
        auto_confirm: bool = False,
        browser: BrowserService | None = None,
        helper_agent: ConversationalAgent | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_router: ToolRouter | None = None,
        skills: tuple[AgentSkillSpec, ...] = (),
        agent_max_steps: int = 12,
        agent_context_token_budget: int = 3000,
    ) -> None:
        self._sessions = sessions
        self._projects = projects
        self._references = references
        self._runner = runner
        self._parser = parser or ChatIntentParser()
        self._auto_confirm = auto_confirm
        self._browser = browser
        self._agent = helper_agent
        self._tools = tool_registry
        self._tool_router = tool_router or (ToolRouter(tool_registry) if tool_registry else None)
        self._skills = skills
        self._agent_max_steps = agent_max_steps
        self._agent_context_token_budget = agent_context_token_budget

    def start_session(self, project_id: str | None = None) -> ChatSession:
        project = self._projects.load(project_id)
        draft = self._apply_project(TaskDraft(), project)
        session = ChatSession(
            id=uuid.uuid4().hex,
            created_at=utc_now(),
            updated_at=utc_now(),
            project_id=project_id,
            task_draft=draft,
            pending_questions=self._questions_for(draft),
        )
        return self._sessions.create(session)

    def resume_session(self, session_id: str) -> ChatSession:
        identifier = self._sessions.last_id() if session_id == "last" else session_id
        if identifier is None:
            raise ValidationError("No saved chat session found")
        return self._sessions.get(identifier)

    def get_status(self, session_id: str) -> ChatResponse:
        session = self._sessions.get(session_id)
        return ChatResponse(self._format_status(session), session, command="status")

    def get_plan(self, session_id: str) -> ChatResponse:
        session = self._sessions.get(session_id)
        plan = session.plan_summary or self._runner.preview_plan(session.task_draft)
        if not plan:
            message = "Le plan n'est pas encore construit."
        else:
            message = "\n".join(f"{index}. {item}" for index, item in enumerate(plan, start=1))
            session = self._save(replace(session, plan_summary=plan))
        return ChatResponse(message, session, command="plan")

    def add_reference(self, session_id: str, path: Path) -> ChatResponse:
        session = self._sessions.get(session_id)
        try:
            document_id = self._references.add_pdf(path)
            sources = tuple(dict.fromkeys((*session.selected_sources, document_id)))
            message = (
                "Cette référence est déjà indexée."
                if document_id in session.selected_sources
                else ("Référence ajoutée et indexée. Je peux reprendre la préparation.")
            )
            session = self._save(
                replace(
                    session,
                    selected_sources=sources,
                    turns=(*session.turns, ConversationTurn(ChatRole.USER, f"/add {path}")),
                )
            )
            return ChatResponse(message, session, command="add")
        except HermesError as exc:
            session = self._save(replace(session, status=ChatStatus.ERROR, last_error=str(exc)))
            return ChatResponse(f"Impossible d'ajouter la référence : {exc}", session, "add")

    def run_task(self, session_id: str) -> ChatResponse:
        session = self._sessions.get(session_id)
        missing = self._parser.required_missing(session.task_draft)
        if missing:
            session = self._save(
                replace(session, pending_questions=self._questions_for(session.task_draft))
            )
            return ChatResponse(session.pending_questions[0], session, command="run")
        coverage_message, covered_sources = self._coverage_message(session.task_draft)
        if coverage_message:
            session = self._save(
                replace(
                    session,
                    selected_sources=covered_sources or session.selected_sources,
                    pending_questions=(coverage_message,),
                    status=ChatStatus.DRAFTING,
                )
            )
            return ChatResponse(coverage_message, session, command="run")
        try:
            session = self._save(replace(session, status=ChatStatus.RUNNING, updated_at=utc_now()))
            completed = self._runner.run(session)
            completed = self._save(completed)
            return ChatResponse(self._format_artifacts(completed), completed, command="run")
        except HermesError as exc:
            failed = self._save(replace(session, status=ChatStatus.ERROR, last_error=str(exc)))
            return ChatResponse(
                "La génération a échoué, mais la session est conservée. "
                f"Détail exploitable : {exc}",
                failed,
                command="run",
            )

    def cancel_task(self, session_id: str) -> ChatResponse:
        session = self._save(
            replace(
                self._sessions.get(session_id), status=ChatStatus.CANCELLED, updated_at=utc_now()
            )
        )
        return ChatResponse("Tâche annulée.", session, command="cancel")

    def handle_message(self, session_id: str, message: str) -> ChatResponse:
        session = self._sessions.get(session_id)
        command, argument = self._classify_command(message)
        if command == "help":
            return ChatResponse(self._help(), session, command="help")
        if command == "exit":
            return ChatResponse("Session sauvegardée. À bientôt.", session, "exit", True)
        if command == "status":
            return self.get_status(session_id)
        if command == "plan":
            return self.get_plan(session_id)
        if command == "sources":
            labels = self._references.describe(session.selected_sources)
            return ChatResponse(
                "\n".join(labels) if labels else "Aucune source sélectionnée.", session, "sources"
            )
        if command == "add":
            if not argument:
                return ChatResponse("Indiquez le chemin du PDF à ajouter.", session, "add")
            return self.add_reference(session_id, Path(argument))
        if command == "run":
            return self.run_task(session_id)
        if command == "cancel":
            return self.cancel_task(session_id)
        if command == "new":
            project = self._projects.load(session.project_id)
            reset = self._save(
                replace(
                    session,
                    task_draft=self._apply_project(TaskDraft(), project),
                    active_task="",
                    status=ChatStatus.DRAFTING,
                    pending_questions=(),
                    produced_artifacts=(),
                    plan_summary=(),
                    updated_at=utc_now(),
                )
            )
            return ChatResponse("Nouvelle tâche prête.", reset, "new")
        if command == "save":
            return ChatResponse("Session sauvegardée.", self._save(session), "save")
        if command == "browser":
            return self._handle_browser(session, argument)

        if self._agent is not None and self._tools is not None and self._tool_router is not None:
            return self._handle_agentic_message(session, message)

        project = self._projects.load(session.project_id)
        intent, draft = self._parser.parse_delta(message, session.task_draft, project)
        missing = self._parser.required_missing(draft)
        pending_questions = self._questions_for(draft)
        selected_sources = session.selected_sources
        if not missing:
            coverage_message, covered_sources = self._coverage_message(draft)
            if coverage_message:
                pending_questions = (coverage_message,)
                missing = ("sources",)
            elif covered_sources:
                selected_sources = covered_sources
        status = ChatStatus.READY if not missing else ChatStatus.DRAFTING
        updated = self._save(
            replace(
                session,
                task_draft=replace(draft, unresolved_fields=missing),
                selected_sources=selected_sources,
                turns=(
                    *session.turns,
                    ConversationTurn(ChatRole.USER, message, parsed_intent=intent),
                ),
                pending_questions=pending_questions,
                status=status,
                updated_at=utc_now(),
            )
        )
        if self._auto_confirm and status == ChatStatus.READY:
            return self.run_task(updated.id)
        return ChatResponse(self._next_message(updated), updated)

    def _handle_agentic_message(self, session: ChatSession, message: str) -> ChatResponse:
        agent = self._agent
        tools = self._tools
        tool_router = self._tool_router
        if agent is None or tools is None or tool_router is None:
            raise ValidationError("Agentic chat requires an agent and tool registry")
        project = self._projects.load(session.project_id)
        working = session
        final_message = ""
        intent = None
        for _step in range(self._agent_max_steps):
            selected_tools = tool_router.select(
                message,
                recent_observations=tuple(
                    item.summary for item in working.recent_observations[-3:]
                ),
            )
            context = AgentContext(
                user_message=message,
                draft=working.task_draft,
                project=project,
                session_summary=working.session_summary,
                recent_observations=working.recent_observations[-5:],
                available_skills=self._skills,
                selected_tools=selected_tools,
                permissions=(
                    "filesystem roots are enforced by tools",
                    "browser consequential actions require confirmation",
                    "quality gate cannot be bypassed",
                ),
                token_budget=self._agent_context_token_budget,
            )
            decision, metrics = agent.decide(context)
            intent = parsed_intent_from_decision(decision)
            working = replace(working, agent_metrics=_merge_metrics(working.agent_metrics, metrics))
            if decision.type is AgentDecisionType.UPDATE_STATE:
                draft = apply_task_draft_patch(working.task_draft, decision.patch)
                draft = self._apply_project(draft, project)
                missing = self._parser.required_missing(draft)
                pending = self._questions_for(draft)
                status = ChatStatus.READY if not missing else ChatStatus.DRAFTING
                working = replace(
                    working,
                    task_draft=replace(draft, unresolved_fields=missing),
                    pending_questions=pending,
                    status=status,
                    session_summary=summarize_session(
                        draft, working.session_summary, working.recent_observations
                    ),
                )
                if status is ChatStatus.READY and self._auto_confirm:
                    saved = self._save(self._append_user_turn(working, message, intent))
                    return self.run_task(saved.id)
                continue
            if decision.type in {AgentDecisionType.TOOL_CALL, AgentDecisionType.TOOL_CALLS}:
                observations = list(working.recent_observations)
                selected_sources = working.selected_sources
                for call in decision.tool_calls:
                    try:
                        result = tools.execute(ToolCall(call.tool, call.action, call.arguments))
                    except HermesError as exc:
                        result = {"error": str(exc), "recoverable": True}
                    observation = observation_from_tool(len(observations) + 1, call.tool, result)
                    observations.append(observation)
                    selected_sources = _selected_sources_from_result(selected_sources, result)
                    working = replace(
                        working,
                        agent_metrics=working.agent_metrics.with_tool_call(),
                        selected_sources=selected_sources,
                    )
                working = replace(
                    working,
                    recent_observations=tuple(observations[-8:]),
                    session_summary=summarize_session(
                        working.task_draft, working.session_summary, tuple(observations)
                    ),
                )
                continue
            if decision.type is AgentDecisionType.DELEGATE:
                working = replace(working, agent_metrics=working.agent_metrics.with_delegation())
                if decision.agent in {
                    "generator",
                    "course_generator",
                    "td_generator",
                } or decision.capability in {
                    "generate",
                    "strong_reasoning",
                }:
                    saved = self._save(self._append_user_turn(working, message, intent))
                    return self.run_task(saved.id)
                final_message = "La délégation demandée n'est pas encore disponible dans Hermes."
                break
            if decision.type is AgentDecisionType.ASK_USER:
                final_message = decision.question or "Pouvez-vous préciser votre demande ?"
                working = replace(
                    working, pending_questions=(final_message,), status=ChatStatus.DRAFTING
                )
                break
            if decision.type in {AgentDecisionType.RESPOND, AgentDecisionType.FINISH}:
                final_message = decision.response or self._next_message(working)
                break
        else:
            final_message = (
                "J'ai atteint la limite d'étapes de l'agent sans terminer. "
                "Je m'arrête pour éviter une boucle."
            )
            working = replace(
                working, status=ChatStatus.ERROR, last_error="agent.max_steps reached"
            )

        if not final_message:
            missing = self._parser.required_missing(working.task_draft)
            if not missing:
                coverage_message, covered_sources = self._coverage_message(working.task_draft)
                if coverage_message:
                    working = replace(
                        working,
                        selected_sources=covered_sources or working.selected_sources,
                        pending_questions=(coverage_message,),
                        status=ChatStatus.DRAFTING,
                    )
                elif covered_sources:
                    working = replace(
                        working, selected_sources=covered_sources, status=ChatStatus.READY
                    )
            final_message = self._next_message(working)
        updated = self._save(self._append_user_turn(working, message, intent))
        return ChatResponse(final_message, updated)

    @staticmethod
    def _append_user_turn(
        session: ChatSession, message: str, intent: ParsedIntent | None
    ) -> ChatSession:
        return replace(
            session,
            turns=(
                *session.turns,
                ConversationTurn(ChatRole.USER, message, parsed_intent=intent),
            ),
            updated_at=utc_now(),
        )

    def handle_prompt(self, message: str, *, project_id: str | None = None) -> ChatResponse:
        session = self.start_session(project_id)
        response = self.handle_message(session.id, message)
        if response.session.status == ChatStatus.READY and self._auto_confirm:
            return self.run_task(response.session.id)
        return response

    def _save(self, session: ChatSession) -> ChatSession:
        return self._sessions.save(replace(session, updated_at=utc_now()))

    def _apply_project(self, draft: TaskDraft, project: ProjectContext | None) -> TaskDraft:
        if project is None:
            return replace(draft, unresolved_fields=self._parser.required_missing(draft))
        merged = replace(
            draft,
            subject=draft.subject or project.subject,
            level=draft.level or project.level,
            curriculum=draft.curriculum or project.curriculum,
            track=draft.track or project.track,
            document_format=draft.document_format or project.document_format,
            pedagogical_preferences=tuple(
                dict.fromkeys((*draft.pedagogical_preferences, *project.pedagogical_preferences))
            ),
        )
        return replace(merged, unresolved_fields=self._parser.required_missing(merged))

    def _classify_command(self, raw: str) -> tuple[str, str]:
        text = raw.strip()
        lowered = text.lower()
        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            return (parts[0], parts[1] if len(parts) > 1 else "")
        if re.search(r"\b(lance|demarre|génère|genere|run)\b", lowered):
            return ("run", "")
        if "montre" in lowered and "plan" in lowered:
            return ("plan", "")
        if "reference" in lowered and ("quelle" in lowered or "montre" in lowered):
            return ("sources", "")
        if re.search(r"\b(status|statut|resume|résumé)\b", lowered):
            return ("status", "")
        if re.search(r"\b(annule|cancel)\b", lowered):
            return ("cancel", "")
        if re.search(r"\b(recommence|nouvelle tache|on recommence)\b", lowered):
            return ("new", "")
        if match := re.search(r"(?:ajoute|add)\s+(.+\.pdf)\b", text, re.IGNORECASE):
            return ("add", match.group(1).strip())
        if text.startswith("/browser "):
            return ("browser", text.removeprefix("/browser ").strip())
        if match := re.search(r"\b(?:ouvre|open)\s+(https?://\S+|file://\S+)", text, re.IGNORECASE):
            return ("browser", f"open {match.group(1)}")
        if re.search(r"\b(?:descends?|scroll down)\b", lowered):
            return ("browser", "scroll down")
        if re.search(r"\b(?:monte|scroll up)\b", lowered):
            return ("browser", "scroll up")
        if re.search(r"\b(?:lis|read|inspecte)\b", lowered) and "page" in lowered:
            return ("browser", "read")
        if match := re.search(r"\b(?:clique|click)\s+(e\d+)\b", lowered):
            return ("browser", f"click {match.group(1)}")
        if match := re.search(r"\b(?:telecharge|télécharge|download)\s+(e\d+)?", lowered):
            element = match.group(1) or ""
            return ("browser", f"download {element}".strip())
        return ("message", "")

    def _handle_browser(self, session: ChatSession, argument: str) -> ChatResponse:
        if self._browser is None:
            return ChatResponse(
                "Le navigateur n'est pas activé pour cette session.", session, "message"
            )
        parts = argument.split()
        action = parts[0].lower() if parts else "read"
        try:
            if action in {"open", "navigate"} and len(parts) >= 2:
                observation = self._browser.open(parts[1])
            elif action == "read":
                observation = self._browser.read()
            elif action == "scroll":
                direction = "up" if len(parts) > 1 and parts[1] == "up" else "down"
                observation = self._browser.scroll(direction=direction)
            elif action == "click" and len(parts) >= 2:
                observation = self._browser.click(element_id=parts[1])
            elif action == "download":
                element_id = parts[1] if len(parts) >= 2 else ""
                observation = self._browser.download(element_id=element_id)
                if "add" in argument or "ajoute" in argument:
                    if observation.download is None:
                        return ChatResponse("Aucun téléchargement détecté.", session, "browser")
                    document_id = self._browser.ingest_download(observation.download.id)
                    updated = self._save(
                        replace(
                            session,
                            selected_sources=tuple(
                                dict.fromkeys((*session.selected_sources, document_id))
                            ),
                        )
                    )
                    return ChatResponse(
                        f"PDF téléchargé et ajouté à la bibliothèque : {document_id}",
                        updated,
                        "browser",
                    )
            elif action == "screenshot":
                observation = self._browser.screenshot()
            elif action == "back":
                observation = self._browser.back()
            elif action == "forward":
                observation = self._browser.forward()
            else:
                return ChatResponse("Commande navigateur non reconnue.", session, "browser")
        except Exception as exc:
            return ChatResponse(f"Action navigateur impossible : {exc}", session, "browser")
        return ChatResponse(observation.compact_summary(), session, "browser")

    def _questions_for(self, draft: TaskDraft) -> tuple[str, ...]:
        if "topic" in draft.unresolved_fields or not draft.topic:
            return ("Pour quel module ou chapitre ?",)
        if "outputs" in draft.unresolved_fields or not draft.outputs:
            return ("Souhaitez-vous un cours, un TD, une fiche ou un corrigé ?",)
        return ()

    def _next_message(self, session: ChatSession) -> str:
        if session.pending_questions:
            return session.pending_questions[0]
        return self._ready_summary(session)

    def _coverage_message(self, draft: TaskDraft) -> tuple[str, tuple[str, ...]]:
        if not draft.topic or not draft.outputs:
            return "", ()
        result = self._references.search(draft.topic, top_k=6)
        if result.outcome is SearchOutcome.ENOUGH_EVIDENCE:
            source_ids = tuple(dict.fromkeys(hit.chunk.document_id for hit in result.hits))
            return "", source_ids
        if result.outcome is SearchOutcome.EMPTY_LIBRARY:
            return (
                "Je n'ai pas encore de référence indexée pour traiter ce sujet rigoureusement. "
                "Ajoutez une référence avec /add <path>.",
                (),
            )
        return (
            f"Les références disponibles ne couvrent pas suffisamment « {draft.topic} ». "
            "Ajoutez une référence avec /add <path> ou ajustez la demande.",
            (),
        )

    def _ready_summary(self, session: ChatSession) -> str:
        draft = session.task_draft
        lines = ["J'ai compris :", f"- sujet : {draft.topic}"]
        if draft.subject:
            lines.append(f"- matière : {draft.subject}")
        if draft.level:
            lines.append(f"- niveau : {draft.level}")
        if draft.duration.label():
            lines.append(f"- durée : {draft.duration.label()}")
        lines.append(f"- sorties : {', '.join(draft.outputs)}")
        if draft.constraints:
            lines.append(f"- contraintes : {'; '.join(draft.constraints)}")
        lines.append("Lancer la génération ? [/run]")
        return "\n".join(lines)

    def _format_status(self, session: ChatSession) -> str:
        payload = asdict(session.task_draft)
        lines = [f"Session : {session.id}", f"Statut : {session.status.value}"]
        for key in ("task_type", "subject", "topic", "level", "outputs", "constraints"):
            value = payload.get(key)
            if value:
                lines.append(f"{key}: {value}")
        if session.pending_questions:
            lines.append(f"question: {session.pending_questions[0]}")
        return "\n".join(lines)

    @staticmethod
    def _format_artifacts(session: ChatSession) -> str:
        if not session.produced_artifacts:
            return "Workflow terminé sans artefact déclaré."
        paths = "\n".join(f"- {artifact.path}" for artifact in session.produced_artifacts)
        return f"Artefacts prêts :\n{paths}"

    @staticmethod
    def _help() -> str:
        return "\n".join(
            (
                "Commandes : /help, /status, /plan, /sources, /add <path>, /run,",
                "/cancel, /new, /save, /exit, /browser open <url>, /browser read.",
            )
        )


def _merge_metrics(current: AgentMetrics, delta: AgentMetrics) -> AgentMetrics:
    cost: float | None
    if current.estimated_cost_usd is None or delta.estimated_cost_usd is None:
        cost = None
    else:
        cost = current.estimated_cost_usd + delta.estimated_cost_usd
    return AgentMetrics(
        helper_calls=current.helper_calls + delta.helper_calls,
        tool_calls=current.tool_calls + delta.tool_calls,
        tokens_in=current.tokens_in + delta.tokens_in,
        tokens_out=current.tokens_out + delta.tokens_out,
        delegated_calls=current.delegated_calls + delta.delegated_calls,
        estimated_cost_usd=cost,
    )


def _selected_sources_from_result(current: tuple[str, ...], result: object) -> tuple[str, ...]:
    sources = list(current)
    if isinstance(result, dict):
        data = cast("Mapping[str, object]", result)
        document_id = data.get("document_id")
        if isinstance(document_id, str) and document_id not in sources:
            sources.append(document_id)
        for key in ("matches", "hits"):
            values = data.get(key)
            if not isinstance(values, tuple | list):
                continue
            for item in cast("tuple[object, ...] | list[object]", values):
                if isinstance(item, dict):
                    row = cast("Mapping[str, object]", item)
                    value = row.get("document_id")
                    if isinstance(value, str) and value not in sources:
                        sources.append(value)
    return tuple(sources)
