"""Provider-neutral records for a personal mathematical reference library."""

from dataclasses import dataclass
from enum import StrEnum

from hermes_edu.domain.errors import ValidationError

MAX_REFERENCE_QUERY_CHARS = 4000


class ReferenceStatus(StrEnum):
    NEW = "NEW"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
    OUTDATED = "OUTDATED"
    DISABLED = "DISABLED"


class SearchOutcome(StrEnum):
    EMPTY_LIBRARY = "EMPTY_LIBRARY"
    NO_RELEVANT_SOURCE = "NO_RELEVANT_SOURCE"
    ENOUGH_EVIDENCE = "ENOUGH_EVIDENCE"


@dataclass(frozen=True, slots=True)
class Reference:
    document_id: str
    content_hash: str
    filename: str
    title: str
    size_bytes: int
    imported_at: str
    status: ReferenceStatus
    enabled: bool = True
    preferred: bool = False
    chunk_count: int = 0
    error: str = ""
    parser_fingerprint: str = ""
    chunker_fingerprint: str = ""
    embedding_model: str = ""
    embedding_provider: str = ""
    embedding_dimension: int = 0
    index_version: str = ""
    ocr_used: bool = False

    def __post_init__(self) -> None:
        if not self.document_id or len(self.content_hash) != 64 or self.size_bytes < 1:
            raise ValidationError("Reference requires a stable ID, SHA-256 and non-empty PDF")


@dataclass(frozen=True, slots=True)
class MathBlock:
    block_id: str
    block_type: str
    text: str
    page_start: int
    page_end: int
    chapter: str = ""
    section: str = ""
    subsection: str = ""
    number: str = ""
    title: str = ""
    relation: str = ""
    related_block_id: str = ""


@dataclass(frozen=True, slots=True)
class ParsedReference:
    document_id: str
    blocks: tuple[MathBlock, ...]
    ocr_used: bool = False
    source_latex: str = ""


@dataclass(frozen=True, slots=True)
class MathChunk:
    chunk_id: str
    document_id: str
    block_id: str
    block_type: str
    content: str
    embedding_text: str
    page_start: int
    page_end: int
    chapter: str = ""
    section: str = ""
    subsection: str = ""
    number: str = ""
    title: str = ""
    parent_id: str = ""
    part_number: int = 1
    parts_count: int = 1
    relation: str = ""
    related_block_id: str = ""


@dataclass(frozen=True, slots=True)
class ReferenceFilters:
    document_ids: tuple[str, ...] = ()
    block_types: tuple[str, ...] = ()
    chapter: str = ""
    section: str = ""
    preferred_only: bool = False


@dataclass(frozen=True, slots=True)
class ReferenceHit:
    chunk: MathChunk
    document_title: str
    score: float


@dataclass(frozen=True, slots=True)
class ReferenceSearchResult:
    outcome: SearchOutcome
    hits: tuple[ReferenceHit, ...] = ()
    query: str = ""
