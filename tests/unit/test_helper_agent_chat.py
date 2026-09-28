from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

from hermes_edu.application.ports.chat import (
    ChatReferencePort,
    ChatSessionRepositoryPort,
    ChatTaskRunnerPort,
    ProjectContextPort,
)
from hermes_edu.application.services.chat_tools import FileSearchTool, ReferenceTool
from hermes_edu.application.services.tools import HermesTool, ToolRegistry, ToolRouter
from hermes_edu.application.use_cases.chat import ChatService
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.agent import (
    AgentContext,
    AgentDecision,
    AgentDecisionType,
    AgentMetrics,
    AgentToolCall,
    AgentToolSpec,
)
from hermes_edu.domain.models.chat import (
    ChatSession,
    ChatStatus,
    ProducedArtifact,
    ProjectContext,
    TaskDraft,
)
from hermes_edu.domain.models.reference import (
    MathChunk,
    ReferenceHit,
    ReferenceSearchResult,
    SearchOutcome,
)
from hermes_edu.persistence.repositories.chat_json import JSONChatSessionRepository


class QueueAgent:
    def __init__(self, *decisions: AgentDecision) -> None:
        self.decisions = list(decisions)
        self.contexts: list[AgentContext] = []

    def decide(self, context: AgentContext) -> tuple[AgentDecision, AgentMetrics]:
        self.contexts.append(context)
        decision = (
            self.decisions.pop(0)
            if self.decisions
            else AgentDecision(AgentDecisionType.RESPOND, response="ok")
        )
        return decision, AgentMetrics(
            helper_calls=1, tokens_in=20, tokens_out=8, estimated_cost_usd=0.001
        )


class MemorySessions(ChatSessionRepositoryPort):
    def __init__(self) -> None:
        self.saved: dict[str, ChatSession] = {}

    def create(self, session: ChatSession) -> ChatSession:
        return self.save(session)

    def save(self, session: ChatSession) -> ChatSession:
        self.saved[session.id] = session
        return session

    def get(self, session_id: str) -> ChatSession:
        return self.saved[session_id]

    def last_id(self) -> str | None:
        return next(reversed(self.saved), None) if self.saved else None


class Projects(ProjectContextPort):
    def load(self, project_id: str | None) -> ProjectContext | None:
        if project_id == "ensam-analyse1":
            return ProjectContext(
                project_id,
                institution="ENSAM",
                subject="Analyse 1",
                level="ENSAM CP1",
                curriculum=project_id,
                track="CP1",
            )
        return None


class References(ChatReferencePort):
    def add_pdf(self, path: Path) -> str:
        return "doc-1"

    def describe(self, document_ids: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(f"{item} - Reference" for item in document_ids)

    def search(self, query: str, *, top_k: int | None = None) -> ReferenceSearchResult:
        chunk = MathChunk(
            "chunk-1",
            "doc-1",
            "block-1",
            "definition",
            f"Contenu sur {query}",
            f"Contenu sur {query}",
            1,
            1,
        )
        return ReferenceSearchResult(
            SearchOutcome.ENOUGH_EVIDENCE,
            (ReferenceHit(chunk, "Reference", 0.9),),
            query,
        )


class Runner(ChatTaskRunnerPort):
    def __init__(self) -> None:
        self.runs = 0

    def run(self, session: ChatSession) -> ChatSession:
        self.runs += 1
        return replace(
            session,
            status=ChatStatus.COMPLETED,
            produced_artifacts=(ProducedArtifact("workspace/chat/td.tex", "tex"),),
        )

    def preview_plan(self, draft: TaskDraft) -> tuple[str, ...]:
        return ("Plan",) if draft.topic else ()


class RecordingTool(HermesTool):
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self._name = name
        self.fail = fail
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    @property
    def name(self) -> str:
        return self._name

    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(self._name, f"{self._name} test tool", {"search": "search"})

    def execute(self, action: str, arguments: Mapping[str, object]) -> object:
        self.calls.append((action, arguments))
        if self.fail:
            raise ValidationError("tool failed")
        return {
            "document_id": f"doc-{self._name}",
            "matches": [{"document_id": f"doc-{self._name}"}],
        }


def agentic_service(
    agent: QueueAgent, registry: ToolRegistry, runner: Runner | None = None
) -> tuple[ChatService, MemorySessions, Runner]:
    sessions = MemorySessions()
    actual_runner = runner or Runner()
    return (
        ChatService(
            sessions=sessions,
            projects=Projects(),
            references=References(),
            runner=actual_runner,
            helper_agent=agent,
            tool_registry=registry,
            tool_router=ToolRouter(registry, max_tools=4),
            agent_max_steps=4,
        ),
        sessions,
        actual_runner,
    )


def test_helper_agent_can_choose_file_search_tool(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    pdf = tmp_path / "data" / "Cours-Fourier.pdf"
    pdf.write_bytes(b"%PDF")
    registry = ToolRegistry((FileSearchTool(root=tmp_path, allowed_roots=(Path("data"),)),))
    agent = QueueAgent(
        AgentDecision(
            AgentDecisionType.TOOL_CALL,
            tool_calls=(
                AgentToolCall("files", "search", {"query": "Fourier", "extensions": ["pdf"]}),
            ),
        ),
        AgentDecision(AgentDecisionType.RESPOND, response="J'ai retrouvé f1."),
    )
    chat, _, _ = agentic_service(agent, registry)

    response = chat.handle_message(chat.start_session().id, "cherche mon fichier Fourier")

    assert "f1" in response.message
    assert response.session.recent_observations[0].kind == "files"
    assert "Cours-Fourier.pdf" in response.session.recent_observations[0].summary


def test_helper_agent_can_choose_browser_tool() -> None:
    browser = RecordingTool("browser")
    registry = ToolRegistry((browser,))
    agent = QueueAgent(
        AgentDecision(
            AgentDecisionType.TOOL_CALL,
            tool_calls=(AgentToolCall("browser", "open", {"url": "https://example.test"}),),
        ),
        AgentDecision(AgentDecisionType.RESPOND, response="Page ouverte."),
    )
    chat, _, _ = agentic_service(agent, registry)

    response = chat.handle_message(chat.start_session().id, "cherche le programme sur internet")

    assert browser.calls == [("open", {"url": "https://example.test"})]
    assert response.message == "Page ouverte."


def test_multiple_tools_can_be_chained_from_observation() -> None:
    files = RecordingTool("files")
    documents = RecordingTool("documents")
    registry = ToolRegistry((files, documents))
    agent = QueueAgent(
        AgentDecision(
            AgentDecisionType.TOOL_CALL,
            tool_calls=(AgentToolCall("files", "search", {"query": "Fourier"}),),
        ),
        AgentDecision(
            AgentDecisionType.TOOL_CALL,
            tool_calls=(AgentToolCall("documents", "search", {"query": "Parseval"}),),
        ),
        AgentDecision(AgentDecisionType.RESPOND, response="Parseval est présent."),
    )
    chat, _, _ = agentic_service(agent, registry)

    response = chat.handle_message(chat.start_session().id, "Fourier Parseval")

    assert files.calls and documents.calls
    assert len(response.session.recent_observations) == 2
    assert response.message == "Parseval est présent."


def test_taskdraft_is_updated_progressively_by_agent_patch() -> None:
    registry = ToolRegistry(())
    agent = QueueAgent(
        AgentDecision(
            AgentDecisionType.UPDATE_STATE,
            patch={"topic": "Intégrales", "outputs.add": ["course"], "duration.sessions": 4},
        ),
        AgentDecision(AgentDecisionType.RESPOND, response="Brouillon mis à jour."),
    )
    chat, _, _ = agentic_service(agent, registry)

    response = chat.handle_message(
        chat.start_session("ensam-analyse1").id, "cours integrales 4 séances"
    )

    assert response.session.task_draft.topic == "Intégrales"
    assert response.session.task_draft.subject == "Analyse 1"
    assert response.session.task_draft.duration.sessions == 4


def test_true_ambiguity_can_trigger_one_question() -> None:
    registry = ToolRegistry(())
    agent = QueueAgent(
        AgentDecision(AgentDecisionType.ASK_USER, question="Cours, TD ou recherche de référence ?")
    )
    chat, _, _ = agentic_service(agent, registry)

    response = chat.handle_message(chat.start_session().id, "le devoir")

    assert response.session.pending_questions == ("Cours, TD ou recherche de référence ?",)


def test_tool_router_does_not_inject_all_tools() -> None:
    registry = ToolRegistry(
        (
            RecordingTool("files"),
            RecordingTool("documents"),
            RecordingTool("references"),
            RecordingTool("browser"),
            RecordingTool("latex"),
            RecordingTool("exam"),
        )
    )
    selected = ToolRouter(registry, max_tools=4).select("cherche mon PDF Fourier")

    names = {tool.name for tool in selected}
    assert "files" in names
    assert "latex" not in names
    assert len(selected) < len(registry.names())


def test_status_does_not_call_helper_agent() -> None:
    agent = QueueAgent(AgentDecision(AgentDecisionType.RESPOND, response="unused"))
    chat, _, _ = agentic_service(agent, ToolRegistry(()))
    session = chat.start_session()

    chat.handle_message(session.id, "/status")

    assert agent.contexts == []


def test_max_steps_stops_infinite_agent_loop() -> None:
    references = RecordingTool("references")
    agent = QueueAgent(
        *(
            AgentDecision(
                AgentDecisionType.TOOL_CALL,
                tool_calls=(AgentToolCall("references", "search", {"query": "x"}),),
            )
            for _ in range(6)
        )
    )
    chat, _, _ = agentic_service(agent, ToolRegistry((references,)))

    response = chat.handle_message(chat.start_session().id, "boucle")

    assert response.session.status == ChatStatus.ERROR
    assert "limite" in response.message


def test_tool_error_is_returned_as_recoverable_observation() -> None:
    failing = RecordingTool("files", fail=True)
    agent = QueueAgent(
        AgentDecision(
            AgentDecisionType.TOOL_CALL,
            tool_calls=(AgentToolCall("files", "search", {"query": "x"}),),
        ),
        AgentDecision(AgentDecisionType.RESPOND, response="Je peux récupérer l'erreur."),
    )
    chat, _, _ = agentic_service(agent, ToolRegistry((failing,)))

    response = chat.handle_message(chat.start_session().id, "cherche")

    assert "tool failed" in response.session.recent_observations[0].summary
    assert response.message == "Je peux récupérer l'erreur."


def test_delegation_to_generator_uses_existing_runner() -> None:
    registry = ToolRegistry(())
    runner = Runner()
    agent = QueueAgent(
        AgentDecision(
            AgentDecisionType.UPDATE_STATE,
            patch={"topic": "Intégrales", "outputs.add": ["tutorial"]},
        ),
        AgentDecision(AgentDecisionType.DELEGATE, agent="generator"),
    )
    chat, _, _ = agentic_service(agent, registry, runner)

    response = chat.handle_message(chat.start_session().id, "crée le TD")

    assert runner.runs == 1
    assert response.session.status == ChatStatus.COMPLETED


def test_agent_metrics_are_accumulated() -> None:
    tool = RecordingTool("files")
    agent = QueueAgent(
        AgentDecision(
            AgentDecisionType.TOOL_CALL,
            tool_calls=(AgentToolCall("files", "search", {"query": "x"}),),
        ),
        AgentDecision(AgentDecisionType.RESPOND, response="ok"),
    )
    chat, _, _ = agentic_service(agent, ToolRegistry((tool,)))

    response = chat.handle_message(chat.start_session().id, "cherche")

    assert response.session.agent_metrics.helper_calls == 2
    assert response.session.agent_metrics.tool_calls == 1
    assert response.session.agent_metrics.tokens_in == 40


def test_filesystem_policy_blocks_outside_allowed_root(tmp_path: Path) -> None:
    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"secret")
    tool = FileSearchTool(root=tmp_path, allowed_roots=(Path("data"),))

    try:
        tool.execute("stat", {"path": str(outside)})
    except ValidationError as exc:
        assert "outside allowed roots" in str(exc)
    else:
        raise AssertionError("outside path should be rejected")


def test_session_summary_is_restorable(tmp_path: Path) -> None:
    repo = JSONChatSessionRepository(tmp_path)
    session = ChatSession(
        id="s1",
        created_at="2026-09-28T00:00:00+00:00",
        updated_at="2026-09-28T00:00:00+00:00",
        session_summary="topic=Intégrales; outputs=course",
        produced_artifacts=(ProducedArtifact("workspace/out.tex", "tex"),),
    )

    repo.save(session)
    restored = repo.get("s1")

    assert restored.session_summary == "topic=Intégrales; outputs=course"
    assert restored.produced_artifacts[0].path == "workspace/out.tex"


def test_reference_tool_keeps_observations_compact() -> None:
    tool = ReferenceTool(References())

    result = tool.execute("search", {"query": "Intégrales", "top_k": 5})

    assert isinstance(result, dict)
    compact = cast("dict[str, object]", result)
    assert len(str(compact)) < 1200
