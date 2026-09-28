"""Centralized version decisions for the reference pipeline."""

from dataclasses import dataclass
from hashlib import sha256


def fingerprint(*parts: str) -> str:
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class ReferencePipelineVersions:
    parser: str
    ocr: str
    chunker: str
    embedding_model: str
    index: str

    def parser_fingerprint(self, *, ocr_used: bool) -> str:
        return fingerprint(self.parser, self.ocr if ocr_used else "text-layer")

    def chunker_fingerprint(self, parser_fingerprint: str) -> str:
        return fingerprint(parser_fingerprint, self.chunker)

    def vector_fingerprint(self, dimension: int) -> str:
        return fingerprint(self.embedding_model, str(dimension), self.index)
