"""Document output contract used by the TD use case."""

from typing import Protocol

from hermes_edu.domain.models.document import Artifact, TDDraft
from hermes_edu.domain.models.source import SourceReference


class DocumentPort(Protocol):
    def render(
        self, draft: TDDraft, sources: tuple[SourceReference, ...], *, thread_id: str
    ) -> Artifact: ...

    def compile(self, tex_artifact: Artifact) -> Artifact | None: ...
