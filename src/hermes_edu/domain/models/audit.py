"""Structured findings that govern revision decisions."""

from dataclasses import dataclass

from hermes_edu.domain.enums import Severity
from hermes_edu.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class AuditIssue:
    severity: Severity
    category: str
    exercise_index: int
    explanation: str

    def __post_init__(self) -> None:
        if not self.category.strip() or not self.explanation.strip() or self.exercise_index < 0:
            raise ValidationError("Audit issues need category, location and explanation")
