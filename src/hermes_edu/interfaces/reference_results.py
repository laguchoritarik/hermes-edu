"""Compact presentation of reference evidence for CLI and MCP callers."""

from hermes_edu.domain.models.reference import MathChunk, ReferenceSearchResult


def reference_chunk_payload(chunk: MathChunk) -> dict[str, object]:
    """Keep only content and provenance needed by a caller."""
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "block_type": chunk.block_type,
        "block_number": chunk.number,
        "chapter": chunk.chapter,
        "section": chunk.section,
        "subsection": chunk.subsection,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "content": chunk.content,
        "relation": chunk.relation,
        "related_block_id": chunk.related_block_id,
        "parent_id": chunk.parent_id,
        "part_number": chunk.part_number,
        "parts_count": chunk.parts_count,
    }


def reference_search_payload(result: ReferenceSearchResult) -> dict[str, object]:
    """Expose citation fields without repeating the enriched embedding text."""
    return {
        "outcome": result.outcome.value,
        "query": result.query,
        "hits": [
            {
                **reference_chunk_payload(hit.chunk),
                "document_title": hit.document_title,
                "semantic_score": hit.score,
            }
            for hit in result.hits
        ],
    }
