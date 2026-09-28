"""Conversation state for chat-driven educational workflows."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.agent import AgentMetrics, AgentObservation


def utc_now() -> str:
    """Return a stable ISO timestamp for persisted chat state."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class ChatStatus(StrEnum):
    DRAFTING = "drafting"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class DurationSpec:
    sessions: int | None = None
    minutes_per_session: int | None = None

    def __post_init__(self) -> None:
        if self.sessions is not None and not 1 <= self.sessions <= 40:
            raise ValidationError("Session count must be between 1 and 40")
        if self.minutes_per_session is not None and not 15 <= self.minutes_per_session <= 360:
            raise ValidationError("Session duration must be between 15 and 360 minutes")

    def label(self) -> str:
        if self.sessions and self.minutes_per_session:
            hours, minutes = divmod(self.minutes_per_session, 60)
            return f"{self.sessions} x {hours}h{minutes:02d}"
        if self.sessions:
            return f"{self.sessions} seances"
        return ""


@dataclass(frozen=True, slots=True)
class TaskDraft:
    task_type: str = ""
    subject: str = ""
    topic: str = ""
    level: str = ""
    audience: str = ""
    duration: DurationSpec = field(default_factory=DurationSpec)
    outputs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    pedagogical_preferences: tuple[str, ...] = ()
    source_policy: str = ""
    document_format: str = ""
    curriculum: str = ""
    track: str = ""
    exercise_count: int | None = None
    section_count: int | None = None
    metadata: dict[str, str] = field(default_factory=lambda: {})
    unresolved_fields: tuple[str, ...] = ()
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.exercise_count is not None and not 1 <= self.exercise_count <= 40:
            raise ValidationError("Exercise count must be between 1 and 40")
        if self.section_count is not None and not 1 <= self.section_count <= 12:
            raise ValidationError("Section count must be between 1 and 12")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("Draft confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ParsedIntent:
    name: str
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=lambda: {})


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    role: ChatRole
    content: str
    timestamp: str = field(default_factory=utc_now)
    parsed_intent: ParsedIntent | None = None
    metadata: dict[str, str] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValidationError("Conversation turns need non-empty content")


@dataclass(frozen=True, slots=True)
class ProducedArtifact:
    path: str
    kind: str = ""


@dataclass(frozen=True, slots=True)
class ChatSession:
    id: str
    created_at: str
    updated_at: str
    project_id: str | None = None
    turns: tuple[ConversationTurn, ...] = ()
    task_draft: TaskDraft = field(default_factory=TaskDraft)
    active_task: str = ""
    status: ChatStatus = ChatStatus.DRAFTING
    selected_sources: tuple[str, ...] = ()
    pending_questions: tuple[str, ...] = ()
    produced_artifacts: tuple[ProducedArtifact, ...] = ()
    plan_summary: tuple[str, ...] = ()
    last_error: str = ""
    session_summary: str = ""
    recent_observations: tuple[AgentObservation, ...] = ()
    agent_metrics: AgentMetrics = field(default_factory=AgentMetrics)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValidationError("Chat session id is required")


@dataclass(frozen=True, slots=True)
class ProjectContext:
    project_id: str
    institution: str = ""
    subject: str = ""
    level: str = ""
    curriculum: str = ""
    track: str = ""
    pedagogical_preferences: tuple[str, ...] = ()
    document_format: str = ""


ChatCommand = Literal[
    "help",
    "status",
    "plan",
    "sources",
    "add",
    "run",
    "cancel",
    "new",
    "save",
    "exit",
    "browser",
    "message",
]


@dataclass(frozen=True, slots=True)
class ChatResponse:
    message: str
    session: ChatSession
    command: ChatCommand = "message"
    should_exit: bool = False
