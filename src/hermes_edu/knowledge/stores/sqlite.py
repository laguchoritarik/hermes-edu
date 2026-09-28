"""SQLite source/chunk index with versioned local vectors and provenance."""

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from pydantic import TypeAdapter

from hermes_edu.application.ports.embeddings import EmbeddingPort
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.source import SourceReference
from hermes_edu.knowledge.chunking.recursive import chunk_document
from hermes_edu.knowledge.models import NormalizedDocument, StoredCandidate

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
 source_id TEXT PRIMARY KEY, title TEXT NOT NULL, location TEXT NOT NULL,
 license TEXT NOT NULL, curriculum TEXT NOT NULL, track TEXT NOT NULL,
 subject TEXT NOT NULL, kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
 chunk_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 section TEXT NOT NULL, text TEXT NOT NULL, content_hash TEXT NOT NULL,
 embedding_model TEXT NOT NULL, vector_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source_id);
"""


class SQLiteKnowledgeStore:
    """Versioned source and vector persistence; unchanged chunks are not re-embedded."""

    def __init__(
        self, path: Path, embedding: EmbeddingPort, *, chunk_size: int = 1200, overlap: int = 150
    ) -> None:
        self._path = path
        self._embedding = embedding
        self._chunk_size = chunk_size
        self._overlap = overlap
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self._path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @property
    def embedding(self) -> EmbeddingPort:
        return self._embedding

    def index(self, document: NormalizedDocument) -> int:
        """Replace one source atomically and embed only changed chunks."""
        chunks = chunk_document(document, chunk_size=self._chunk_size, overlap=self._overlap)
        with self._connect() as connection:
            known = {
                row[0]: (row[1], row[2], row[3])
                for row in connection.execute(
                    "SELECT chunk_id, content_hash, embedding_model, vector_json FROM chunks WHERE source_id=?",
                    (document.source.source_id,),
                )
            }
            changed = [
                chunk
                for chunk in chunks
                if chunk.chunk_id not in known
                or known[chunk.chunk_id][:2] != (chunk.content_hash, self._embedding.model_id)
            ]
            vectors = self._embedding.embed(tuple(chunk.text for chunk in changed))
            if len(vectors) != len(changed):
                raise ValueError("Embedding adapter returned the wrong number of vectors")
            connection.execute(
                """INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET title=excluded.title,
                location=excluded.location, license=excluded.license,
                curriculum=excluded.curriculum, track=excluded.track,
                subject=excluded.subject, kind=excluded.kind""",
                (
                    document.source.source_id,
                    document.source.title,
                    document.source.location,
                    document.source.license,
                    document.context.curriculum,
                    document.context.track,
                    document.context.subject,
                    document.kind,
                ),
            )
            for chunk, vector in zip(changed, vectors, strict=True):
                connection.execute(
                    """INSERT INTO chunks VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(chunk_id) DO UPDATE SET section=excluded.section,
                    text=excluded.text, content_hash=excluded.content_hash,
                    embedding_model=excluded.embedding_model, vector_json=excluded.vector_json""",
                    (
                        chunk.chunk_id,
                        chunk.source.source_id,
                        chunk.section,
                        chunk.text,
                        chunk.content_hash,
                        self._embedding.model_id,
                        json.dumps(vector),
                    ),
                )
            current_ids = {chunk.chunk_id for chunk in chunks}
            for old_id in known.keys() - current_ids:
                connection.execute("DELETE FROM chunks WHERE chunk_id=?", (old_id,))
        return len(changed)

    def candidates(
        self, context: LearningContext, *, kind: str, embedding_model: str
    ) -> tuple[StoredCandidate, ...]:
        """Load candidates matching source context and embedding version."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT c.chunk_id, c.text, c.section, c.vector_json,
                s.source_id, s.title, s.location, s.license
                FROM chunks c JOIN sources s ON s.source_id=c.source_id
                WHERE s.curriculum=? AND s.track=? AND s.subject=? AND s.kind=?
                AND c.embedding_model=?""",
                (
                    context.curriculum,
                    context.track,
                    context.subject,
                    kind,
                    embedding_model,
                ),
            ).fetchall()
        candidates: list[StoredCandidate] = []
        for chunk_id, text, section, vector_json, source_id, title, location, license in rows:
            candidates.append(
                StoredCandidate(
                    chunk_id=chunk_id,
                    text=text,
                    section=section,
                    source=SourceReference(source_id, title, location, license),
                    vector=TypeAdapter(tuple[float, ...]).validate_json(vector_json),
                )
            )
        return tuple(candidates)
