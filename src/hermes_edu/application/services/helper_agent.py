"""Conversational helper agent over provider-neutral LLM and Hermes tools."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import cast

import structlog

from hermes_edu.application.ports.llm import LLMPort, ModelRequest
from hermes_edu.application.services.chat_intent import ChatIntentParser
from hermes_edu.domain.errors import GenerationError, ValidationError
from hermes_edu.domain.models.agent import (
    AgentContext,
    AgentDecision,
    AgentDecisionType,
    AgentMetrics,
    AgentObservation,
    AgentToolCall,
)
from hermes_edu.domain.models.chat import ParsedIntent, TaskDraft

logger = structlog.get_logger(__name__)


class HelperAgent:
    """LLM-backed conversational orchestrator returning validated decisions."""

    def __init__(
        self,
        llm: LLMPort,
        *,
        max_output_tokens: int = 1200,
        deterministic_fallback: ChatIntentParser | None = None,
    ) -> None:
        self._llm = llm
        self._max_output_tokens = max_output_tokens
        self._fallback = deterministic_fallback or ChatIntentParser()

    def decide(self, context: AgentContext) -> tuple[AgentDecision, AgentMetrics]:
        request = ModelRequest(
            system=_SYSTEM_PROMPT,
            user=json.dumps(_context_payload(context), ensure_ascii=False),
            max_output_tokens=self._max_output_tokens,
            task="helper",
        )
        try:
            response = self._llm.complete_json(request)
            decision = _decision_from_json(response.content)
            return decision, AgentMetrics().with_usage(response.usage)
        except (GenerationError, ValidationError, json.JSONDecodeError) as exc:
            logger.info("helper_agent_fallback", error=str(exc))
            return RuleBasedHelperAgent(self._fallback).decide(context)


class RuleBasedHelperAgent:
    """Offline fallback and unit-test helper with the same decision contract."""

    def __init__(self, parser: ChatIntentParser | None = None) -> None:
        self._parser = parser or ChatIntentParser()

    def decide(self, context: AgentContext) -> tuple[AgentDecision, AgentMetrics]:
        lowered = context.user_message.lower()
        if _is_true_ambiguity(lowered, context):
            return (
                AgentDecision(
                    AgentDecisionType.ASK_USER,
                    question="Voulez-vous préparer un cours, un TD, ou chercher une référence ?",
                    intent_summary="ambiguous_short_request",
                ),
                AgentMetrics(),
            )
        if _ordinal_reference(lowered) and context.recent_observations:
            return (
                AgentDecision(
                    AgentDecisionType.RESPOND,
                    response=_resolve_ordinal(lowered, context.recent_observations),
                    intent_summary="resolve_previous_result",
                ),
                AgentMetrics(),
            )
        if context.recent_observations and context.recent_observations[-1].kind == "documents":
            return (
                AgentDecision(
                    AgentDecisionType.RESPOND,
                    response="J'ai vérifié les documents indexés. "
                    + context.recent_observations[-1].summary[:700],
                    intent_summary="document_search_answer",
                ),
                AgentMetrics(),
            )
        if context.recent_observations and any(
            word in lowered for word in ("parseval", "contient")
        ):
            return (
                AgentDecision(
                    AgentDecisionType.TOOL_CALL,
                    tool_calls=(
                        AgentToolCall(
                            "documents", "search", {"query": context.user_message, "top_k": 5}
                        ),
                    ),
                    intent_summary="document_content_search",
                ),
                AgentMetrics(),
            )
        if any(
            word in lowered
            for word in ("site", "internet", "web", "http", "ministère", "ministere")
        ):
            return (
                AgentDecision(
                    AgentDecisionType.TOOL_CALL,
                    tool_calls=(
                        AgentToolCall(
                            "browser", "open", {"url": _url_or_search(context.user_message)}
                        ),
                    ),
                    skill="web_reference_research",
                    intent_summary="web_reference_research",
                ),
                AgentMetrics(),
            )
        if any(
            word in lowered for word in ("fichier", "file", "pdf", "fourier", "fourrier", "ensam")
        ):
            query = "Fourier" if "four" in lowered else context.user_message
            root_hint = "ENSAM" if "ensam" in lowered else ""
            return (
                AgentDecision(
                    AgentDecisionType.TOOL_CALL,
                    tool_calls=(
                        AgentToolCall(
                            "files",
                            "search",
                            {"query": query, "root_hint": root_hint, "extensions": ["pdf"]},
                        ),
                    ),
                    intent_summary="local_file_search",
                ),
                AgentMetrics(),
            )
        intent, draft = self._parser.parse_delta(
            context.user_message, context.draft, context.project
        )
        if draft != context.draft:
            return (
                AgentDecision(
                    AgentDecisionType.UPDATE_STATE,
                    patch=_patch_from_draft(context.draft, draft),
                    intent_summary=intent.name,
                ),
                AgentMetrics(),
            )
        return (
            AgentDecision(
                AgentDecisionType.RESPOND,
                response="J'ai besoin d'une précision pour avancer.",
                intent_summary="needs_clarification",
            ),
            AgentMetrics(),
        )


def apply_task_draft_patch(draft: TaskDraft, patch: Mapping[str, object]) -> TaskDraft:
    """Apply a bounded patch language emitted by the helper agent."""
    updated = draft
    duration = updated.duration
    if "duration.sessions" in patch:
        duration = replace(duration, sessions=_optional_int(patch["duration.sessions"]))
    if "duration.minutes_per_session" in patch:
        duration = replace(
            duration, minutes_per_session=_optional_int(patch["duration.minutes_per_session"])
        )
    outputs = list(updated.outputs)
    for value in _str_tuple(patch.get("outputs.add")):
        if value not in outputs:
            outputs.append(value)
    for value in _str_tuple(patch.get("outputs.remove")):
        outputs = [item for item in outputs if item != value]
    metadata = dict(updated.metadata)
    raw_metadata = patch.get("metadata")
    if isinstance(raw_metadata, dict):
        metadata.update(
            {
                str(key): str(value)
                for key, value in cast("dict[object, object]", raw_metadata).items()
            }
        )
    fields: dict[str, object] = {
        "duration": duration,
        "outputs": tuple(outputs),
        "metadata": metadata,
        "confidence": min(
            1.0, max(updated.confidence, _float(patch.get("confidence"), updated.confidence))
        ),
    }
    for key in (
        "task_type",
        "subject",
        "topic",
        "level",
        "audience",
        "source_policy",
        "document_format",
        "curriculum",
        "track",
    ):
        if key in patch:
            fields[key] = str(patch[key]).strip()
    for key in ("exercise_count", "section_count"):
        if key in patch:
            fields[key] = _optional_int(patch[key])
    for key in ("constraints", "pedagogical_preferences", "unresolved_fields"):
        if key in patch:
            fields[key] = _str_tuple(patch[key])
    return replace(updated, **fields)


def summarize_session(
    draft: TaskDraft, previous: str, observations: tuple[AgentObservation, ...]
) -> str:
    parts = [previous] if previous else []
    if draft.topic:
        parts.append(f"topic={draft.topic}")
    if draft.subject:
        parts.append(f"subject={draft.subject}")
    if draft.level:
        parts.append(f"level={draft.level}")
    if draft.duration.sessions:
        parts.append(f"sessions={draft.duration.sessions}")
    if draft.outputs:
        parts.append(f"outputs={','.join(draft.outputs)}")
    for observation in observations[-3:]:
        parts.append(f"{observation.id}:{observation.summary[:160]}")
    summary = "; ".join(dict.fromkeys(part for part in parts if part))
    return summary[:1200]


def observation_from_tool(index: int, tool: str, result: object) -> AgentObservation:
    summary = _compact_result(result)
    return AgentObservation(f"o{index}", tool, summary, {"tool": tool})


def parsed_intent_from_decision(decision: AgentDecision) -> ParsedIntent:
    return ParsedIntent(
        decision.intent_summary or decision.type.value.lower(),
        0.8,
        {"skill": decision.skill} if decision.skill else {},
    )


def _context_payload(context: AgentContext) -> dict[str, object]:
    return {
        "user_message": context.user_message,
        "task_draft": asdict(context.draft),
        "project": asdict(context.project) if context.project else None,
        "session_summary": context.session_summary,
        "recent_observations": tuple(asdict(item) for item in context.recent_observations[-5:]),
        "available_skills": tuple(asdict(item) for item in context.available_skills),
        "selected_tools": tuple(asdict(item) for item in context.selected_tools),
        "permissions": context.permissions,
        "decision_schema": {
            "type": "TOOL_CALL|TOOL_CALLS|UPDATE_STATE|ASK_USER|DELEGATE|RESPOND|FINISH",
            "tool_calls": [{"tool": "files", "action": "search", "arguments": {}}],
            "patch": {"topic": "Intégrales", "outputs.add": ["course"]},
            "question": "one concise question if needed",
            "response": "final user-facing response",
            "agent": "generator|validator|strong_reasoning",
        },
    }


def _decision_from_json(content: str) -> AgentDecision:
    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValidationError("Helper decision must be a JSON object")
    data = cast("dict[str, object]", raw)
    decision_type = AgentDecisionType(str(data.get("type", "")))
    call_source = data.get("tool_calls") or data.get("tools")
    calls_raw: list[object] = (
        cast("list[object]", call_source) if isinstance(call_source, list) else []
    )
    if data.get("tool") and not calls_raw:
        calls_raw = [
            {
                "tool": data.get("tool"),
                "action": data.get("action", ""),
                "arguments": data.get("arguments", {}),
            }
        ]
    calls = tuple(_tool_call(item) for item in calls_raw)
    if decision_type is AgentDecisionType.TOOL_CALL and len(calls) != 1:
        raise ValidationError("TOOL_CALL requires exactly one tool call")
    return AgentDecision(
        decision_type,
        tool_calls=calls,
        patch=cast(
            "Mapping[str, object]", data.get("patch") if isinstance(data.get("patch"), dict) else {}
        ),
        question=str(data.get("question", "")),
        response=str(data.get("response", "")),
        agent=str(data.get("agent", "")),
        capability=str(data.get("capability", "")),
        task=cast(
            "Mapping[str, object]", data.get("task") if isinstance(data.get("task"), dict) else {}
        ),
        intent_summary=str(data.get("intent_summary", "")),
        skill=str(data.get("skill", "")),
    )


def _tool_call(value: object) -> AgentToolCall:
    raw = cast("dict[str, object]", value if isinstance(value, dict) else {})
    arguments = raw.get("arguments")
    return AgentToolCall(
        str(raw.get("tool", "")),
        str(raw.get("action", "")),
        cast("Mapping[str, object]", arguments if isinstance(arguments, dict) else {}),
    )


def _patch_from_draft(previous: TaskDraft, draft: TaskDraft) -> dict[str, object]:
    patch: dict[str, object] = {}
    for key in (
        "task_type",
        "subject",
        "topic",
        "level",
        "audience",
        "source_policy",
        "document_format",
        "curriculum",
        "track",
        "exercise_count",
        "section_count",
        "constraints",
        "pedagogical_preferences",
    ):
        if getattr(previous, key) != getattr(draft, key):
            patch[key] = getattr(draft, key)
    if previous.outputs != draft.outputs:
        patch["outputs.add"] = tuple(item for item in draft.outputs if item not in previous.outputs)
        patch["outputs.remove"] = tuple(
            item for item in previous.outputs if item not in draft.outputs
        )
    if previous.duration.sessions != draft.duration.sessions:
        patch["duration.sessions"] = draft.duration.sessions
    if previous.duration.minutes_per_session != draft.duration.minutes_per_session:
        patch["duration.minutes_per_session"] = draft.duration.minutes_per_session
    patch["confidence"] = draft.confidence
    return patch


def _compact_result(result: object) -> str:
    if hasattr(result, "compact_summary"):
        return str(result.compact_summary())[:1000]  # type: ignore[attr-defined]
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, default=str)[:1000]
    return str(result)[:1000]


def _str_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, list | tuple):
        return tuple(
            str(item) for item in cast("list[object] | tuple[object, ...]", value) if str(item)
        )
    return (str(value),)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _float(value: object, default: float) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return default


def _url_or_search(message: str) -> str:
    for part in message.split():
        if part.startswith("http://") or part.startswith("https://"):
            return part
    return "https://www.google.com/search?q=" + message.replace(" ", "+")


def _is_true_ambiguity(lowered: str, context: AgentContext) -> bool:
    return len(lowered.split()) <= 3 and not context.recent_observations and not context.draft.topic


def _ordinal_reference(lowered: str) -> bool:
    return any(word in lowered for word in ("deuxième", "deuxieme", "second", "2"))


def _resolve_ordinal(lowered: str, observations: tuple[AgentObservation, ...]) -> str:
    target = "f2" if any(word in lowered for word in ("deux", "second", "2")) else "f1"
    for observation in reversed(observations):
        if target in observation.summary:
            return f"Je sélectionne {target} dans la dernière liste de résultats."
    return "Je sélectionne le deuxième élément de la dernière liste de résultats."


_SYSTEM_PROMPT = """You are Hermes-Edu Helper Agent.
Return only one compact JSON decision. Do not include chain-of-thought.
You orchestrate deterministic Hermes services: update TaskDraft, select tools,
use compact observations, ask one concise question only when ambiguity matters,
or delegate ready generation/validation. Never invent tool results. Do not
bypass filesystem, browser, source, quality-gate or confirmation policies."""
