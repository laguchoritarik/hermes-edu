"""Educational context for source selection."""

from dataclasses import dataclass

from hermes_edu.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class LearningContext:
    curriculum: str
    track: str
    subject: str = "mathematics"

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.curriculum, self.track, self.subject)):
            raise ValidationError("Curriculum, track and subject must be non-empty")
