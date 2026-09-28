"""Offline local-index integration tests."""

from pathlib import Path

import pytest

from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.source import SourceReference
from hermes_edu.knowledge.embeddings.base import DeterministicEmbedding
from hermes_edu.knowledge.ingestion.base import load_document
from hermes_edu.knowledge.models import NormalizedDocument, StoredCandidate
from hermes_edu.knowledge.retrieval.vector import SQLiteVectorRetriever
from hermes_edu.knowledge.stores.sqlite import SQLiteKnowledgeStore


class CountingEmbedding(DeterministicEmbedding):
    calls = 0

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls += len(texts)
        return super().embed(texts)


class RecordingEmbedding(DeterministicEmbedding):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self._events.append("embed")
        return super().embed(texts)


class RecordingStore(SQLiteKnowledgeStore):
    def __init__(self, path: Path, embedding: DeterministicEmbedding, events: list[str]) -> None:
        super().__init__(path, embedding)
        self._events = events
        self.calls: list[tuple[LearningContext, str, str]] = []

    def candidates(
        self, context: LearningContext, *, kind: str, embedding_model: str
    ) -> tuple[StoredCandidate, ...]:
        self._events.append("search")
        self.calls.append((context, kind, embedding_model))
        return super().candidates(context, kind=kind, embedding_model=embedding_model)


class FixedEmbedding:
    model_id = "fixed"

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        vector = (float("nan"), 0.0) if texts == ("invalid",) else (1.0, 0.0)
        return tuple(vector for _ in texts)


class FixedStore(SQLiteKnowledgeStore):
    def __init__(self, path: Path, candidates: tuple[StoredCandidate, ...]) -> None:
        super().__init__(path, DeterministicEmbedding())
        self._fixed_candidates = candidates

    def candidates(
        self, context: LearningContext, *, kind: str, embedding_model: str
    ) -> tuple[StoredCandidate, ...]:
        return self._fixed_candidates


def test_index_reuses_unchanged_vectors_and_preserves_provenance(tmp_path: Path) -> None:
    embedding = CountingEmbedding()
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.db", embedding, chunk_size=30, overlap=5)
    context = LearningContext("sample", "MP")
    document = NormalizedDocument(
        SourceReference("s1", "Synthetic", "local", "CC0"),
        context,
        "curriculum",
        "eigenvalues and eigenspaces diagonalization repeated eigenvalue",
    )
    assert store.index(document) > 0
    first_calls = embedding.calls
    assert store.index(document) == 0
    assert embedding.calls == first_calls
    retriever = SQLiteVectorRetriever(store, embedding)
    hits = retriever.retrieve("eigenvalues", context, kind="curriculum", top_k=1)
    assert len(hits) == 1
    assert hits[0].source.source_id == "s1"
    assert hits[0].chunk_id.startswith("s1:")
    assert (
        retriever.retrieve(
            "eigenvalues", LearningContext("other", "MP"), kind="curriculum", top_k=1
        )
        == ()
    )


def test_ingestion_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "private.md"
    outside.write_text("private")
    with pytest.raises(ValidationError):
        load_document(
            outside,
            allowed_root=root,
            source_id="private",
            title="Private",
            license="none",
            context=LearningContext("sample", "MP"),
            kind="knowledge",
        )


def test_retrieval_embeds_before_search_and_filters_context_and_score(tmp_path: Path) -> None:
    events: list[str] = []
    embedding = RecordingEmbedding(events)
    store = RecordingStore(tmp_path / "knowledge.db", embedding, events)
    context = LearningContext("official-mp", "MP")
    store.index(
        NormalizedDocument(
            SourceReference("official", "Official MP", "https://education.example/mp", "public"),
            context,
            "curriculum",
            "Integration dependent on a parameter.",
        )
    )
    events.clear()

    hits = SQLiteVectorRetriever(store, embedding, min_score=-1).retrieve(
        "parameter integral", context, kind="curriculum", top_k=3
    )

    assert events == ["embed", "search"]
    assert store.calls == [(context, "curriculum", embedding.model_id)]
    assert hits[0].chunk_id.startswith("official:")
    assert hits[0].source.location == "https://education.example/mp"
    assert (
        SQLiteVectorRetriever(store, embedding, min_score=1).retrieve(
            "unrelated topic", context, kind="curriculum", top_k=3
        )
        == ()
    )


def test_ingestion_prefers_valid_source_url_for_provenance(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    path = root / "official.md"
    path.write_text("Official curriculum excerpt")

    document = load_document(
        path,
        allowed_root=root,
        source_id="official-mp",
        title="Official MP",
        license="public",
        context=LearningContext("mp", "MP"),
        kind="curriculum",
        source_url="https://www.education.gouv.fr/programme-mp",
    )

    assert document.source.location == "https://www.education.gouv.fr/programme-mp"
    with pytest.raises(ValidationError, match="absolute http"):
        load_document(
            path,
            allowed_root=root,
            source_id="official-mp",
            title="Official MP",
            license="public",
            context=LearningContext("mp", "MP"),
            kind="curriculum",
            source_url="file:///private/programme.pdf",
        )


def test_retrieval_uses_cosine_and_skips_invalid_embedding_vectors(tmp_path: Path) -> None:
    source = SourceReference("source", "Source", "https://example.test/source", "public")
    candidates = (
        StoredCandidate("aligned", "Aligned", "", source, (0.9, 0.1)),
        StoredCandidate("large", "Large", "", source, (100.0, 100.0)),
        StoredCandidate("zero", "Zero", "", source, (0.0, 0.0)),
        StoredCandidate("non-finite", "Invalid", "", source, (float("inf"), 0.0)),
    )
    embedding = FixedEmbedding()
    retriever = SQLiteVectorRetriever(FixedStore(tmp_path / "fixed.db", candidates), embedding)

    hits = retriever.retrieve(
        "parameter integral", LearningContext("mp", "MP"), kind="curriculum", top_k=4
    )

    assert [hit.chunk_id for hit in hits] == ["aligned", "large"]
    assert hits[0].score == pytest.approx(0.9938837347)
    assert (
        retriever.retrieve("invalid", LearningContext("mp", "MP"), kind="curriculum", top_k=4) == ()
    )
    with pytest.raises(ValueError, match="finite"):
        SQLiteVectorRetriever(
            FixedStore(tmp_path / "nan.db", candidates), embedding, min_score=float("nan")
        )
