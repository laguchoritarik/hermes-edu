"""Immutable course content and review contracts, independent of rendering frameworks."""

from dataclasses import dataclass

from hermes_edu.domain.enums import Severity
from hermes_edu.domain.errors import ValidationError

_COURSE_BLOCK_KINDS = (
    "text",
    "definition",
    "theorem",
    "proposition",
    "lemma",
    "corollary",
    "result",
    "proof",
    "example",
    "method",
    "remark",
    "exercise",
    "solution",
)


@dataclass(frozen=True, slots=True)
class CourseRequest:
    topic: str
    curriculum: str
    track: str = "MP"
    section_count: int = 6
    document_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.topic.strip()
            or len(self.topic) > 200
            or not self.track.strip()
            or not self.curriculum.strip()
        ):
            raise ValidationError("Course topic (1-200 characters) and track are required")
        if isinstance(self.section_count, bool) or not 1 <= self.section_count <= 12:
            raise ValidationError("Course section count must be between 1 and 12")


@dataclass(frozen=True, slots=True)
class PlannedSection:
    title: str
    objective: str
    curriculum_source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.objective.strip():
            raise ValidationError("Section title and objective are required")


@dataclass(frozen=True, slots=True)
class CoursePlan:
    title: str
    sections: tuple[PlannedSection, ...]

    def __post_init__(self) -> None:
        if not self.title.strip() or not 1 <= len(self.sections) <= 12:
            raise ValidationError("A course plan needs a title and 1-12 sections")


@dataclass(frozen=True, slots=True)
class CourseBlock:
    kind: str
    text: str
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in _COURSE_BLOCK_KINDS:
            allowed_kinds = ", ".join(_COURSE_BLOCK_KINDS)
            raise ValidationError(
                f"Unknown course block kind {self.kind!r}. Allowed kinds: {allowed_kinds}"
            )
        if not self.text.strip() or len(self.text) > 12000:
            raise ValidationError("Course blocks need 1-12000 characters")


@dataclass(frozen=True, slots=True)
class CourseSection:
    title: str
    blocks: tuple[CourseBlock, ...]
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.title.strip() or not 1 <= len(self.blocks) <= 60 or not self.source_ids:
            raise ValidationError("A course section needs a title, 1-60 blocks and citations")
        if sum(len(block.text) for block in self.blocks) > 24000:
            raise ValidationError("Course section exceeds 24000 characters")


@dataclass(frozen=True, slots=True)
class CourseDraft:
    title: str
    sections: tuple[CourseSection, ...]

    def __post_init__(self) -> None:
        if not self.title.strip() or not 1 <= len(self.sections) <= 12:
            raise ValidationError("A course needs a title and 1-12 sections")


@dataclass(frozen=True, slots=True)
class CourseIssue:
    severity: Severity
    section_index: int
    explanation: str
    section_title: str = ""

    def __post_init__(self) -> None:
        if self.section_index < 1 or not self.explanation.strip():
            raise ValidationError("Course issue needs a positive section index and explanation")
