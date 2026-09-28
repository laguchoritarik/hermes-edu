"""Normalized local source and chunk transfer records."""

from dataclasses import dataclass

from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.source import SourceReference


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    source: SourceReference
    context: LearningContext
    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: str
    source: SourceReference
    context: LearningContext
    kind: str
    section: str
    text: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class StoredCandidate:
    chunk_id: str
    text: str
    section: str
    source: SourceReference
    vector: tuple[float, ...]
