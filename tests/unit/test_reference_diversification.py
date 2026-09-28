"""Unit coverage for deterministic post-HNSW reference diversification."""

from hermes_edu.application.use_cases.reference_library import diversify_reference_hits
from hermes_edu.domain.models.reference import MathChunk, ReferenceHit


def _hit(identifier: str, content: str, score: float) -> ReferenceHit:
    return ReferenceHit(
        MathChunk(
            chunk_id=identifier,
            document_id="doc",
            block_id=identifier,
            block_type="definition",
            content=content,
            embedding_text=content,
            page_start=1,
            page_end=1,
            section="Structures",
        ),
        "Cours",
        score,
    )


def test_post_hnsw_diversification_discards_quasi_duplicate_chunks() -> None:
    retained, eliminated = diversify_reference_hits(
        (
            _hit("a", "Une base est une famille libre et génératrice.", 0.95),
            _hit("b", "Une base est une famille libre et génératrice.", 0.94),
            _hit("c", "Un projecteur est un endomorphisme idempotent.", 0.90),
        ),
        2,
    )

    assert [hit.chunk.chunk_id for hit in retained] == ["a", "c"]
    assert [hit.chunk.chunk_id for hit in eliminated] == ["b"]
