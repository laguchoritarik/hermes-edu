"""Bounded cosine retrieval over a context-filtered local store."""

import math

from hermes_edu.application.ports.embeddings import EmbeddingPort
from hermes_edu.application.ports.retriever import RetrieverPort
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.source import RetrievedChunk
from hermes_edu.knowledge.stores.sqlite import SQLiteKnowledgeStore


class SQLiteVectorRetriever(RetrieverPort):
    def __init__(
        self,
        store: SQLiteKnowledgeStore,
        embedding: EmbeddingPort,
        *,
        min_score: float | None = None,
    ) -> None:
        if min_score is not None and (not math.isfinite(min_score) or not -1.0 <= min_score <= 1.0):
            raise ValueError("min_score must be a finite value between -1 and 1")
        self._store = store
        self._embedding = embedding
        self._min_score = min_score

    def retrieve(
        self, query: str, context: LearningContext, *, kind: str, top_k: int
    ) -> tuple[RetrievedChunk, ...]:
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        query_vector = self._embedding.embed((query,))[0]
        query_norm = _norm(query_vector)
        if query_norm is None:
            return ()
        candidates = self._store.candidates(
            context, kind=kind, embedding_model=self._embedding.model_id
        )
        hits: list[RetrievedChunk] = []
        for candidate in candidates:
            if len(candidate.vector) != len(query_vector):
                continue
            candidate_norm = _norm(candidate.vector)
            if candidate_norm is None:
                continue
            score = math.fsum(
                a * b for a, b in zip(query_vector, candidate.vector, strict=True)
            ) / (query_norm * candidate_norm)
            hits.append(
                RetrievedChunk(
                    chunk_id=candidate.chunk_id,
                    text=candidate.text,
                    source=candidate.source,
                    score=score,
                    section=candidate.section,
                )
            )
        if self._min_score is not None:
            hits = [hit for hit in hits if hit.score >= self._min_score]
        hits.sort(key=lambda hit: (-hit.score, hit.chunk_id))
        return tuple(hits[:top_k])


def _norm(vector: tuple[float, ...]) -> float | None:
    """Return a finite non-zero Euclidean norm for valid embedding coordinates."""
    if not vector or not all(math.isfinite(value) for value in vector):
        return None
    norm = math.sqrt(math.fsum(value * value for value in vector))
    return norm if math.isfinite(norm) and norm > 0 else None
