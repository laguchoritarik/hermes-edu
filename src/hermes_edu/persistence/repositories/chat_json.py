"""JSON-backed chat session persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

from hermes_edu.application.ports.chat import ChatSessionRepositoryPort
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.agent import AgentMetrics, AgentObservation
from hermes_edu.domain.models.chat import (
    ChatRole,
    ChatSession,
    ChatStatus,
    ConversationTurn,
    DurationSpec,
    ParsedIntent,
    ProducedArtifact,
    TaskDraft,
)


class JSONChatSessionRepository(ChatSessionRepositoryPort):
    """Persist compact structured chat state without model prompts."""

    def __init__(self, session_dir: Path) -> None:
        self._session_dir = session_dir

    def create(self, session: ChatSession) -> ChatSession:
        if self._path(session.id).exists():
            raise ValidationError(f"Chat session already exists: {session.id}")
        return self.save(session)

    def save(self, session: ChatSession) -> ChatSession:
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._path(session.id).write_text(
            json.dumps(asdict(session), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self._session_dir / "last").write_text(session.id, encoding="utf-8")
        return session

    def get(self, session_id: str) -> ChatSession:
        path = self._path(session_id)
        if not path.is_file():
            raise ValidationError(f"No chat session found for {session_id}")
        return _session_from_json(json.loads(path.read_text(encoding="utf-8")))

    def last_id(self) -> str | None:
        marker = self._session_dir / "last"
        if not marker.is_file():
            return None
        value = marker.read_text(encoding="utf-8").strip()
        return value or None

    def _path(self, session_id: str) -> Path:
        if "/" in session_id or "\\" in session_id or not session_id.strip():
            raise ValidationError("Invalid chat session id")
        return self._session_dir / f"{session_id}.json"


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    items = cast("list[object] | tuple[object, ...]", value)
    return tuple(item for item in items if isinstance(item, str))


def _metadata(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    mapping = cast("dict[object, object]", value)
    return {str(key): str(item) for key, item in mapping.items()}


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _str(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    return value if isinstance(value, str) else ""


def _draft(value: object) -> TaskDraft:
    raw = cast(dict[str, object], value if isinstance(value, dict) else {})
    duration_raw = raw.get("duration")
    duration = cast(dict[str, object], duration_raw if isinstance(duration_raw, dict) else {})
    return TaskDraft(
        task_type=_str(raw, "task_type"),
        subject=_str(raw, "subject"),
        topic=_str(raw, "topic"),
        level=_str(raw, "level"),
        audience=_str(raw, "audience"),
        duration=DurationSpec(
            sessions=_optional_int(duration.get("sessions")),
            minutes_per_session=_optional_int(duration.get("minutes_per_session")),
        ),
        outputs=_string_tuple(raw.get("outputs")),
        constraints=_string_tuple(raw.get("constraints")),
        pedagogical_preferences=_string_tuple(raw.get("pedagogical_preferences")),
        source_policy=_str(raw, "source_policy"),
        document_format=_str(raw, "document_format"),
        curriculum=_str(raw, "curriculum"),
        track=_str(raw, "track"),
        exercise_count=_optional_int(raw.get("exercise_count")),
        section_count=_optional_int(raw.get("section_count")),
        metadata=_metadata(raw.get("metadata")),
        unresolved_fields=_string_tuple(raw.get("unresolved_fields")),
        confidence=_float(raw.get("confidence")),
    )


def _turn(value: object) -> ConversationTurn:
    raw = cast(dict[str, object], value if isinstance(value, dict) else {})
    intent_raw = raw.get("parsed_intent")
    intent: ParsedIntent | None = None
    if isinstance(intent_raw, dict):
        intent_data = cast("dict[str, object]", intent_raw)
        intent = ParsedIntent(
            _str(intent_data, "name"),
            _float(intent_data.get("confidence")),
            _metadata(intent_data.get("metadata")),
        )
    return ConversationTurn(
        ChatRole(_str(raw, "role") or "user"),
        _str(raw, "content"),
        _str(raw, "timestamp"),
        intent,
        _metadata(raw.get("metadata")),
    )


def _artifact(value: object) -> ProducedArtifact:
    raw = cast(dict[str, object], value if isinstance(value, dict) else {})
    return ProducedArtifact(_str(raw, "path"), _str(raw, "kind"))


def _observation(value: object) -> AgentObservation:
    raw = cast(dict[str, object], value if isinstance(value, dict) else {})
    return AgentObservation(
        _str(raw, "id"),
        _str(raw, "kind"),
        _str(raw, "summary"),
        _metadata(raw.get("metadata")),
    )


def _metrics(value: object) -> AgentMetrics:
    raw = cast(dict[str, object], value if isinstance(value, dict) else {})
    cost = raw.get("estimated_cost_usd")
    return AgentMetrics(
        helper_calls=_optional_int(raw.get("helper_calls")) or 0,
        tool_calls=_optional_int(raw.get("tool_calls")) or 0,
        tokens_in=_optional_int(raw.get("tokens_in")) or 0,
        tokens_out=_optional_int(raw.get("tokens_out")) or 0,
        delegated_calls=_optional_int(raw.get("delegated_calls")) or 0,
        estimated_cost_usd=float(cost)
        if isinstance(cost, int | float) and not isinstance(cost, bool)
        else None
        if cost is None
        else 0.0,
    )


def _session_from_json(value: object) -> ChatSession:
    raw = cast(dict[str, object], value if isinstance(value, dict) else {})
    turns_raw = raw.get("turns")
    artifacts_raw = raw.get("produced_artifacts")
    observations_raw = raw.get("recent_observations")
    project_id_raw = raw.get("project_id")
    project_id = project_id_raw if isinstance(project_id_raw, str) else None
    return ChatSession(
        id=_str(raw, "id"),
        created_at=_str(raw, "created_at"),
        updated_at=_str(raw, "updated_at"),
        project_id=project_id,
        turns=tuple(_turn(item) for item in cast(list[object], turns_raw or [])),
        task_draft=_draft(raw.get("task_draft")),
        active_task=_str(raw, "active_task"),
        status=ChatStatus(_str(raw, "status") or ChatStatus.DRAFTING.value),
        selected_sources=_string_tuple(raw.get("selected_sources")),
        pending_questions=_string_tuple(raw.get("pending_questions")),
        produced_artifacts=tuple(
            _artifact(item) for item in cast(list[object], artifacts_raw or [])
        ),
        plan_summary=_string_tuple(raw.get("plan_summary")),
        last_error=_str(raw, "last_error"),
        session_summary=_str(raw, "session_summary"),
        recent_observations=tuple(
            _observation(item) for item in cast(list[object], observations_raw or [])
        ),
        agent_metrics=_metrics(raw.get("agent_metrics")),
    )
