"""Validated request for a mathematics exercise sheet."""

from dataclasses import dataclass

from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.curriculum import LearningContext


@dataclass(frozen=True, slots=True)
class TDRequest:
    topic: str
    context: LearningContext
    exercise_count: int = 3
    include_solutions: bool = True

    def __post_init__(self) -> None:
        if not self.topic.strip() or len(self.topic) > 200:
            raise ValidationError("Topic must contain 1-200 characters")
        if isinstance(self.exercise_count, bool) or not 1 <= self.exercise_count <= 12:
            raise ValidationError("Exercise count must be between 1 and 12")
        if self.context.subject.lower() != "mathematics":
            raise ValidationError("v0.1 supports mathematics only")
