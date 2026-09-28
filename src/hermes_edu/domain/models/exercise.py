"""Structured TD plan and generated exercises."""

from dataclasses import dataclass

from hermes_edu.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class PlannedExercise:
    title: str
    objective: str
    difficulty: int

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.title, self.objective)):
            raise ValidationError("Planned exercises need a title and objective")
        if isinstance(self.difficulty, bool) or not 1 <= self.difficulty <= 5:
            raise ValidationError("Difficulty must be between 1 and 5")


@dataclass(frozen=True, slots=True)
class Exercise:
    title: str
    statement: str
    solution: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.title, self.statement)):
            raise ValidationError("Exercises need a title and statement")
