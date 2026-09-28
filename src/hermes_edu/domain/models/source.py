"""Provenance records remain independent of a store implementation."""

from dataclasses import dataclass

from hermes_edu.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_id: str
    title: str
    location: str
    license: str

    def __post_init__(self) -> None:
        if not self.source_id or not self.title or not self.location:
            raise ValidationError("Source identity, title and location are required")


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    source: SourceReference
    score: float
    section: str = ""

    def __post_init__(self) -> None:
        if not self.chunk_id or not self.text.strip():
            raise ValidationError("Retrieved chunks need an ID and text")
