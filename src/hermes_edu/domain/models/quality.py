"""Provider-neutral quality assurance records for generated educational documents."""

from dataclasses import dataclass
from enum import StrEnum

from hermes_edu.domain.enums import Severity
from hermes_edu.domain.errors import ValidationError


class CoverageStatus(StrEnum):
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"


class QualityStatus(StrEnum):
    PASS = "PASS"
    DRAFT = "DRAFT"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class CoverageItem:
    concept: str
    mandatory: bool
    supporting_source_ids: tuple[str, ...] = ()
    supporting_chunk_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    status: CoverageStatus = CoverageStatus.MISSING

    def __post_init__(self) -> None:
        if not self.concept.strip() or not 0 <= self.confidence <= 1:
            raise ValidationError("Coverage items require a concept and confidence in [0, 1]")


@dataclass(frozen=True, slots=True)
class SectionCoverage:
    section_id: str
    title: str
    required_topics: tuple[str, ...]
    evidence_status: CoverageStatus
    evidence_score: float
    items: tuple[CoverageItem, ...]

    def __post_init__(self) -> None:
        if not self.section_id.strip() or not self.title.strip():
            raise ValidationError("Section coverage requires an ID and title")
        if not 0 <= self.evidence_score <= 1:
            raise ValidationError("Section evidence score must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class QualityIssue:
    category: str
    severity: Severity
    message: str
    section_index: int = 0
    block_index: int = 0
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.category.strip() or not self.message.strip():
            raise ValidationError("Quality issues require a category and message")
        if self.section_index < 0 or self.block_index < 0:
            raise ValidationError("Quality issue indexes must be non-negative")


@dataclass(frozen=True, slots=True)
class RenderQualityReport:
    critical_warnings: tuple[str, ...] = ()
    suspicious_text: tuple[str, ...] = ()
    page_count: int = 0


@dataclass(frozen=True, slots=True)
class QualityReport:
    status: QualityStatus
    coverage: tuple[SectionCoverage, ...]
    source_gaps: tuple[QualityIssue, ...] = ()
    math_issues: tuple[QualityIssue, ...] = ()
    notation_issues: tuple[QualityIssue, ...] = ()
    duplicates: tuple[QualityIssue, ...] = ()
    latex_issues: tuple[QualityIssue, ...] = ()
    render_issues: tuple[QualityIssue, ...] = ()
    metadata_contamination: tuple[QualityIssue, ...] = ()
    content_policy_issues: tuple[QualityIssue, ...] = ()
    blockers: tuple[QualityIssue, ...] = ()
    warnings: tuple[QualityIssue, ...] = ()
    render: RenderQualityReport = RenderQualityReport()
