"""TD content and artifact metadata."""

from dataclasses import dataclass
from string import hexdigits

from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.exercise import Exercise, PlannedExercise
from hermes_edu.domain.models.source import SourceReference
from hermes_edu.domain.models.usage import ModelUsage


@dataclass(frozen=True, slots=True)
class TDPlan:
    title: str
    exercises: tuple[PlannedExercise, ...]

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.exercises:
            raise ValidationError("A TD plan needs a title and exercises")


@dataclass(frozen=True, slots=True)
class TDDraft:
    title: str
    exercises: tuple[Exercise, ...]

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.exercises:
            raise ValidationError("A TD draft needs a title and exercises")


@dataclass(frozen=True, slots=True)
class Artifact:
    kind: str
    path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if (
            not self.kind
            or not self.path
            or len(self.sha256) != 64
            or any(character not in hexdigits for character in self.sha256)
            or self.size_bytes < 1
        ):
            raise ValidationError("Artifact requires kind, path, SHA-256 and non-empty content")


@dataclass(frozen=True, slots=True)
class TDResult:
    thread_id: str
    draft: TDDraft
    sources: tuple[SourceReference, ...]
    artifacts: tuple[Artifact, ...]
    revisions: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    estimated_cost_usd: float | None
    usage: tuple[ModelUsage, ...]

    def __post_init__(self) -> None:
        if not self.thread_id or self.revisions < 0 or not self.artifacts:
            raise ValidationError("TD result requires a thread, artifacts and valid revision count")
