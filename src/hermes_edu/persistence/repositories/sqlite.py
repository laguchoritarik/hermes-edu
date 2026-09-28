"""Durable reference metadata and reusable parse/chunk artifacts in the existing SQLite DB."""

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from pydantic import TypeAdapter

from hermes_edu.domain.models.reference import (
    MathChunk,
    ParsedReference,
    Reference,
    ReferenceFilters,
    ReferenceStatus,
)


class SQLiteReferenceRepository:
    """One writer transaction serializes imports of identical content across processes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: ContextVar[sqlite3.Connection | None] = ContextVar(
            "reference_transaction", default=None
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Reference database schema is newer than this Hermes version")
            if version == 0:
                script = (
                    files("hermes_edu.persistence.migrations")
                    .joinpath("0001_reference_library.sql")
                    .read_text(encoding="utf-8")
                )
                connection.executescript(script)

    @contextmanager
    def transaction(self) -> Generator[None]:
        connection = sqlite3.connect(self._path, timeout=120)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        token = self._connection.set(connection)
        try:
            yield
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            self._connection.reset(token)
            connection.close()

    def _db(self) -> sqlite3.Connection:
        connection = self._connection.get()
        if connection is None:
            raise RuntimeError("Reference repository operation needs a transaction")
        return connection

    @staticmethod
    def _reference(row: sqlite3.Row) -> Reference:
        return Reference(
            document_id=str(row["document_id"]),
            content_hash=str(row["content_hash"]),
            filename=str(row["filename"]),
            title=str(row["title"]),
            size_bytes=int(row["size_bytes"]),
            imported_at=str(row["imported_at"]),
            status=ReferenceStatus(str(row["status"])),
            enabled=bool(row["enabled"]),
            preferred=bool(row["preferred"]),
            chunk_count=int(row["chunk_count"]),
            error=str(row["error"]),
            parser_fingerprint=str(row["parser_fingerprint"]),
            chunker_fingerprint=str(row["chunker_fingerprint"]),
            embedding_model=str(row["embedding_model"]),
            embedding_provider=str(row["embedding_provider"]),
            embedding_dimension=int(row["embedding_dimension"]),
            index_version=str(row["index_version"]),
            ocr_used=bool(row["ocr_used"]),
        )

    def get_by_hash(self, content_hash: str) -> Reference | None:
        row = (
            self._db()
            .execute("SELECT * FROM reference_documents WHERE content_hash=?", (content_hash,))
            .fetchone()
        )
        return self._reference(row) if row else None

    def get(self, document_id: str) -> Reference | None:
        row = (
            self._db()
            .execute("SELECT * FROM reference_documents WHERE document_id=?", (document_id,))
            .fetchone()
        )
        return self._reference(row) if row else None

    def list(self) -> tuple[Reference, ...]:
        rows = (
            self._db()
            .execute("SELECT * FROM reference_documents ORDER BY imported_at DESC, document_id")
            .fetchall()
        )
        return tuple(self._reference(row) for row in rows)

    def save(self, reference: Reference) -> None:
        columns = tuple(asdict(reference).keys())
        values = list(asdict(reference).values())
        values[columns.index("status")] = reference.status.value
        self._db().execute(
            f"INSERT INTO reference_documents ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
            f"ON CONFLICT(document_id) DO UPDATE SET {','.join(f'{column}=excluded.{column}' for column in columns if column != 'document_id')}",
            values,
        )

    def parsed(self, document_id: str, fingerprint: str) -> ParsedReference | None:
        row = (
            self._db()
            .execute(
                "SELECT payload_json FROM reference_parsed WHERE document_id=? AND fingerprint=?",
                (document_id, fingerprint),
            )
            .fetchone()
        )
        return TypeAdapter(ParsedReference).validate_json(row[0]) if row else None

    def save_parsed(self, parsed: ParsedReference, fingerprint: str) -> None:
        self._db().execute(
            "INSERT OR REPLACE INTO reference_parsed VALUES (?,?,?)",
            (parsed.document_id, fingerprint, json.dumps(asdict(parsed))),
        )

    def chunks(self, document_id: str, fingerprint: str) -> tuple[MathChunk, ...]:
        rows = (
            self._db()
            .execute(
                "SELECT payload_json FROM reference_chunks WHERE document_id=? AND fingerprint=? ORDER BY rowid",
                (document_id, fingerprint),
            )
            .fetchall()
        )
        adapter = TypeAdapter(MathChunk)
        return tuple(adapter.validate_json(row[0]) for row in rows)

    def save_chunks(self, chunks: tuple[MathChunk, ...], fingerprint: str) -> None:
        self._db().executemany(
            "INSERT OR REPLACE INTO reference_chunks VALUES (?,?,?,?,?,?,?)",
            (
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    fingerprint,
                    chunk.block_type,
                    chunk.chapter,
                    chunk.section,
                    json.dumps(asdict(chunk)),
                )
                for chunk in chunks
            ),
        )

    def vector_labels(
        self, chunk_ids: tuple[str, ...], model: str, dimension: int, index_version: str
    ) -> dict[str, tuple[int, bool]]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = (
            self._db()
            .execute(
                f"SELECT chunk_id,label,indexed FROM reference_vector_labels WHERE chunk_id IN ({placeholders}) "
                "AND model=? AND dimension=? AND index_version=?",
                (*chunk_ids, model, dimension, index_version),
            )
            .fetchall()
        )
        return {str(row["chunk_id"]): (int(row["label"]), bool(row["indexed"])) for row in rows}

    def vector_dimension(self, chunk_ids: tuple[str, ...], model: str, index_version: str) -> int:
        if not chunk_ids:
            return 0
        row = (
            self._db()
            .execute(
                f"SELECT dimension FROM reference_vector_labels WHERE chunk_id IN ({','.join('?' for _ in chunk_ids)}) "
                "AND model=? AND index_version=? LIMIT 1",
                (*chunk_ids, model, index_version),
            )
            .fetchone()
        )
        return int(row[0]) if row else 0

    def allocate_labels(
        self, chunk_ids: tuple[str, ...], model: str, dimension: int, index_version: str
    ) -> dict[str, int]:
        self._db().executemany(
            "INSERT OR IGNORE INTO reference_vector_labels "
            "(chunk_id,model,dimension,index_version,indexed) VALUES (?,?,?,?,0)",
            ((chunk_id, model, dimension, index_version) for chunk_id in chunk_ids),
        )
        return {
            chunk_id: label
            for chunk_id, (label, _) in self.vector_labels(
                chunk_ids, model, dimension, index_version
            ).items()
        }

    def mark_indexed(self, labels: tuple[int, ...]) -> None:
        self._db().executemany(
            "UPDATE reference_vector_labels SET indexed=1 WHERE label=?",
            ((label,) for label in labels),
        )

    def eligible_labels(
        self, filters: ReferenceFilters, model: str, dimension: int, index_version: str
    ) -> tuple[int, ...]:
        conditions = [
            "d.enabled=1",
            "d.status IN ('READY','OUTDATED')",
            "v.indexed=1",
            "c.fingerprint=d.chunker_fingerprint",
            "v.model=d.embedding_model",
            "v.dimension=d.embedding_dimension",
            "v.index_version=d.index_version",
        ]
        conditions.extend(("v.model=?", "v.dimension=?", "v.index_version=?"))
        parameters: list[object] = [model, dimension, index_version]
        if filters.document_ids:
            conditions.append(f"d.document_id IN ({','.join('?' for _ in filters.document_ids)})")
            parameters.extend(filters.document_ids)
        if filters.block_types:
            conditions.append(f"c.block_type IN ({','.join('?' for _ in filters.block_types)})")
            parameters.extend(filters.block_types)
        if filters.chapter:
            conditions.append("c.chapter=?")
            parameters.append(filters.chapter)
        if filters.section:
            conditions.append("c.section=?")
            parameters.append(filters.section)
        if filters.preferred_only:
            conditions.append("d.preferred=1")
        rows = (
            self._db()
            .execute(
                "SELECT DISTINCT v.label FROM reference_documents d "
                "JOIN reference_chunks c ON c.document_id=d.document_id "
                "JOIN reference_vector_labels v ON v.chunk_id=c.chunk_id WHERE "
                + " AND ".join(conditions),
                parameters,
            )
            .fetchall()
        )
        return tuple(int(row[0]) for row in rows)

    def chunks_for_labels(self, labels: tuple[int, ...]) -> dict[int, tuple[MathChunk, str]]:
        if not labels:
            return {}
        rows = (
            self._db()
            .execute(
                "SELECT DISTINCT v.label,c.payload_json,d.title FROM reference_vector_labels v "
                "JOIN reference_chunks c ON c.chunk_id=v.chunk_id "
                "JOIN reference_documents d ON d.document_id=c.document_id "
                f"WHERE v.label IN ({','.join('?' for _ in labels)}) AND c.fingerprint=d.chunker_fingerprint "
                "AND v.model=d.embedding_model AND v.dimension=d.embedding_dimension "
                "AND v.index_version=d.index_version AND d.enabled=1",
                labels,
            )
            .fetchall()
        )
        adapter = TypeAdapter(MathChunk)
        return {int(row[0]): (adapter.validate_json(row[1]), str(row[2])) for row in rows}

    def related_chunks(self, chunk_id: str) -> tuple[MathChunk, ...]:
        source = (
            self._db()
            .execute(
                "SELECT c.document_id, json_extract(c.payload_json, '$.block_id') AS block_id, "
                "json_extract(c.payload_json, '$.related_block_id') AS related_block_id "
                "FROM reference_chunks c JOIN reference_documents d ON d.document_id=c.document_id "
                "WHERE c.chunk_id=? AND c.fingerprint=d.chunker_fingerprint AND d.enabled=1 "
                "AND d.status IN ('READY','OUTDATED')",
                (chunk_id,),
            )
            .fetchone()
        )
        if source is None:
            return ()
        rows = (
            self._db()
            .execute(
                "SELECT c.payload_json FROM reference_chunks c "
                "JOIN reference_documents d ON d.document_id=c.document_id "
                "WHERE c.document_id=? AND c.fingerprint=d.chunker_fingerprint "
                "AND d.enabled=1 AND d.status IN ('READY','OUTDATED') AND c.chunk_id<>? "
                "AND (json_extract(c.payload_json, '$.related_block_id')=? "
                "OR json_extract(c.payload_json, '$.block_id')=?) ORDER BY c.rowid",
                (source[0], chunk_id, source[1], source[2]),
            )
            .fetchall()
        )
        adapter = TypeAdapter(MathChunk)
        return tuple(adapter.validate_json(row[0]) for row in rows)

    def all_labels(self, document_id: str) -> tuple[tuple[str, int, int, str], ...]:
        rows = (
            self._db()
            .execute(
                "SELECT DISTINCT v.model,v.dimension,v.label,v.index_version FROM reference_vector_labels v "
                "JOIN reference_chunks c ON c.chunk_id=v.chunk_id WHERE c.document_id=?",
                (document_id,),
            )
            .fetchall()
        )
        return tuple((str(row[0]), int(row[1]), int(row[2]), str(row[3])) for row in rows)

    def prune_vectors(
        self,
        document_id: str,
        active_chunk_ids: tuple[str, ...],
        model: str,
        dimension: int,
        index_version: str,
    ) -> tuple[tuple[str, int, int, str], ...]:
        stale: list[tuple[str, int, int, str]] = []
        active = set(active_chunk_ids)
        rows = (
            self._db()
            .execute(
                "SELECT DISTINCT v.chunk_id,v.model,v.dimension,v.label,v.index_version "
                "FROM reference_vector_labels v JOIN reference_chunks c ON c.chunk_id=v.chunk_id "
                "WHERE c.document_id=?",
                (document_id,),
            )
            .fetchall()
        )
        for row in rows:
            chunk_id, old_model, old_dimension, label, old_index = (
                str(row[0]),
                str(row[1]),
                int(row[2]),
                int(row[3]),
                str(row[4]),
            )
            if chunk_id in active and (old_model, old_dimension, old_index) == (
                model,
                dimension,
                index_version,
            ):
                continue
            stale.append((old_model, old_dimension, label, old_index))
            self._db().execute("DELETE FROM reference_vector_labels WHERE label=?", (label,))
        return tuple(stale)

    def remove(self, document_id: str) -> None:
        self._db().execute(
            "DELETE FROM reference_vector_labels WHERE chunk_id IN "
            "(SELECT chunk_id FROM reference_chunks WHERE document_id=?)",
            (document_id,),
        )
        self._db().execute("DELETE FROM reference_documents WHERE document_id=?", (document_id,))

    def count_active(self) -> int:
        row = (
            self._db()
            .execute(
                "SELECT COUNT(*) FROM reference_documents WHERE enabled=1 AND status IN ('READY','OUTDATED')"
            )
            .fetchone()
        )
        return int(row[0]) if row else 0
