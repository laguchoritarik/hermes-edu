"""Course-specific retrieval and document boundaries."""

from typing import Protocol

from hermes_edu.domain.models.course import CourseDraft
from hermes_edu.domain.models.document import Artifact
from hermes_edu.domain.models.quality import QualityReport
from hermes_edu.domain.models.reference import ReferenceFilters, ReferenceSearchResult
from hermes_edu.domain.models.source import SourceReference


class CourseReferencePort(Protocol):
    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: ReferenceFilters | None = None,
        purpose: str = "",
    ) -> ReferenceSearchResult: ...


class CourseDocumentPort(Protocol):
    def render(
        self,
        draft: CourseDraft,
        sources: tuple[SourceReference, ...],
        *,
        thread_id: str,
    ) -> Artifact: ...
    def compile(self, tex_artifact: Artifact) -> Artifact | None: ...
    def repair_latex(self, tex_artifact: Artifact, diagnostic: str) -> Artifact: ...
    def write_quality_report(
        self, report: QualityReport, *, thread_id: str
    ) -> tuple[Artifact, ...]: ...
