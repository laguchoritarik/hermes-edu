"""Provider-neutral model contract and accounting records."""

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from hermes_edu.domain.errors import GenerationError
from hermes_edu.domain.models.usage import ModelUsage


@dataclass(frozen=True, slots=True)
class ModelRequest:
    system: str
    user: str
    max_output_tokens: int
    task: str
    candidate_offset: int = 0


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str
    usage: ModelUsage
    additional_usages: tuple[ModelUsage, ...] = ()


class LLMPort(Protocol):
    """Return JSON content for a bounded structured generation request."""

    def complete_json(self, request: ModelRequest) -> ModelResponse: ...


@runtime_checkable
class CandidateLLMPort(Protocol):
    """Provide an explicit, ordered set of models for validated completion."""

    def candidates_for(self, request: ModelRequest) -> tuple[LLMPort, ...]: ...


class ModelAttemptError(GenerationError):
    """A rejected provider response whose token usage must still be counted."""

    def __init__(
        self,
        message: str,
        usages: tuple[ModelUsage, ...],
        *,
        timed_out: bool = False,
        returned_outcome: Literal["invalid", "error"] = "error",
        failed_latency_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.usages = usages
        self.timed_out = timed_out
        self.returned_outcome: Literal["invalid", "error"] = returned_outcome
        self.failed_latency_ms = failed_latency_ms


class ModelExhaustedError(GenerationError):
    """All candidates failed; usage remains available to the caller."""

    def __init__(self, message: str, usages: tuple[ModelUsage, ...]) -> None:
        super().__init__(message)
        self.usages = usages


@dataclass(frozen=True, slots=True)
class ModelOutcome:
    task: str
    provider: str
    model: str
    outcome: Literal["validated", "invalid", "error"]
    latency_ms: int
    usage: ModelUsage | None = None
    timed_out: bool = False


class ModelOutcomeStorePort(Protocol):
    """Persist only model identity, outcome and aggregate accounting metadata."""

    def record(self, outcome: ModelOutcome) -> None: ...


@runtime_checkable
class ObservedLLMPort(Protocol):
    """Allow structured validation to account for selected model candidates."""

    def observe(self, outcome: ModelOutcome) -> None: ...

    def identity_for(self, request: ModelRequest, candidate: LLMPort) -> tuple[str, str]: ...
