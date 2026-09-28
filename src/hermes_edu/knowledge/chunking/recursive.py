"""Deterministic paragraph-first chunking with stable IDs."""

import hashlib

from hermes_edu.knowledge.models import KnowledgeChunk, NormalizedDocument


def chunk_document(
    document: NormalizedDocument, *, chunk_size: int = 1200, overlap: int = 150
) -> tuple[KnowledgeChunk, ...]:
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("Chunk size must exceed non-negative overlap")
    text = "\n".join(line.strip() for line in document.text.splitlines() if line.strip())
    chunks: list[KnowledgeChunk] = []
    step = chunk_size - overlap
    for start in range(0, len(text), step):
        segment = text[start : start + chunk_size]
        if not segment:
            break
        digest = hashlib.sha256(segment.encode()).hexdigest()
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"{document.source.source_id}:{start}:{digest[:12]}",
                source=document.source,
                context=document.context,
                kind=document.kind,
                section=str(start),
                text=segment,
                content_hash=digest,
            )
        )
        if start + chunk_size >= len(text):
            break
    return tuple(chunks)
