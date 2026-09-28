"""Import, curate, and search personal PDF references through existing ports."""

import re
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from hermes_edu.application.ports.embeddings import EmbeddingPort
from hermes_edu.application.ports.references import (
    ReferenceChunkerPort,
    ReferenceEventsPort,
    ReferenceFilesPort,
    ReferenceParserPort,
    ReferenceRepositoryPort,
    ReferenceVectorPort,
)
from hermes_edu.application.services.reference_fingerprints import ReferencePipelineVersions
from hermes_edu.domain.errors import GenerationError, HermesError, ValidationError
from hermes_edu.domain.models.reference import (
    MAX_REFERENCE_QUERY_CHARS,
    MathChunk,
    Reference,
    ReferenceFilters,
    ReferenceHit,
    ReferenceSearchResult,
    ReferenceStatus,
    SearchOutcome,
)

_PURPOSE_BLOCKS: dict[str, tuple[str, ...]] = {
    "definition": ("definition",),
    "theorem": ("theorem", "proposition", "lemma", "corollary"),
    "proof": ("proof",),
    "example": ("example", "counterexample"),
    "exercises": ("exercise", "question"),
    "solutions": ("solution",),
}
_DUPLICATE_TEXT_THRESHOLD = 0.92


class ReferenceLibrary:
    """Coordinates durable stage caches and the separate semantic HNSW index."""

    def __init__(
        self,
        *,
        repository: ReferenceRepositoryPort,
        files: ReferenceFilesPort,
        parser: ReferenceParserPort,
        chunker: ReferenceChunkerPort,
        embedding: EmbeddingPort,
        vectors: ReferenceVectorPort,
        events: ReferenceEventsPort,
        versions: ReferencePipelineVersions,
        default_top_k: int = 5,
        max_top_k: int = 30,
        minimum_score: float = 0.35,
        embedding_batch_size: int = 16,
        expected_dimension: int = 0,
        embedding_provider: str = "",
        example_context_alpha: float = 0.8,
    ) -> None:
        if not 1 <= default_top_k <= max_top_k or not -1 <= minimum_score <= 1:
            raise ValueError("Invalid reference retrieval settings")
        if not 0 <= example_context_alpha <= 1:
            raise ValueError("Invalid example context alpha")
        self._repository = repository
        self._files = files
        self._parser = parser
        self._chunker = chunker
        self._embedding = embedding
        self._vectors = vectors
        self._events = events
        self._versions = versions
        self._default_top_k = default_top_k
        self._max_top_k = max_top_k
        self._minimum_score = minimum_score
        self._batch_size = embedding_batch_size
        self._expected_dimension = expected_dimension
        self._embedding_provider = embedding_provider
        self._example_context_alpha = example_context_alpha

    def import_pdf(self, path: Path, *, title: str | None = None) -> Reference:
        content = self._files.read(path)
        return self._import(content, path.name, title=title, force=False)

    def import_pdf_bytes(
        self, content: bytes, filename: str, *, title: str | None = None
    ) -> Reference:
        """Import downloaded PDF bytes through the same reference pipeline."""
        if not filename.lower().endswith(".pdf"):
            raise ValidationError("Reference download must be a PDF filename")
        if not content.startswith(b"%PDF-"):
            raise ValidationError("Reference download is not a valid PDF header")
        return self._import(content, Path(filename).name, title=title, force=False)

    def import_many(self, paths: tuple[Path, ...]) -> tuple[Reference, ...]:
        return tuple(self.import_pdf(path) for path in paths)

    def import_directory(self, directory: Path) -> tuple[Reference, ...]:
        return self.import_many(self._files.list_pdfs(directory))

    def reindex(self, document_id: str) -> Reference:
        with self._repository.transaction():
            reference = self._required(document_id)
        content = self._files.retained(reference.content_hash)
        return self._import(content, reference.filename, title=reference.title, force=True)

    def _import(
        self, content: bytes, filename: str, *, title: str | None, force: bool
    ) -> Reference:
        content_hash = sha256(content).hexdigest()
        document_id = content_hash[:32]
        self._files.retain(content_hash, content)
        failure: Exception | None = None
        result: Reference | None = None
        with self._repository.transaction():
            existing = self._repository.get_by_hash(content_hash)
            reference = existing or Reference(
                document_id,
                content_hash,
                filename,
                title or Path(filename).stem,
                len(content),
                datetime.now(UTC).isoformat(),
                ReferenceStatus.NEW,
            )
            reference = replace(
                reference,
                filename=filename,
                title=title or reference.title,
                size_bytes=len(content),
            )
            if existing and not force and self._is_complete(reference):
                self._repository.save(reference)
                self._events.info(
                    "reference_skip", document_id=document_id, reason="fingerprints_match"
                )
                return reference
            self._repository.save(reference)
            self._events.info(
                "reference_import", document_id=document_id, duplicate=existing is not None
            )
            try:
                result = self._process(reference, content, force=force)
            except (HermesError, OSError, RuntimeError, ValueError) as exc:
                failure = exc
                fallback = (
                    ReferenceStatus.OUTDATED
                    if existing and existing.chunk_count
                    else ReferenceStatus.FAILED
                )
                self._repository.save(replace(reference, status=fallback, error=str(exc)[:500]))
                self._events.warning(
                    "reference_failed", document_id=document_id, error_type=type(exc).__name__
                )
        if failure is not None:
            raise GenerationError(f"Reference ingestion failed: {failure}") from failure
        if result is None:
            raise GenerationError("Reference ingestion returned no result")
        return result

    def _is_complete(self, reference: Reference) -> bool:
        if reference.status not in {ReferenceStatus.READY, ReferenceStatus.DISABLED}:
            return False
        expected_parser = self._versions.parser_fingerprint(ocr_used=reference.ocr_used)
        if (
            reference.parser_fingerprint != expected_parser
            or reference.chunker_fingerprint != self._versions.chunker_fingerprint(expected_parser)
            or reference.embedding_model != self._embedding.model_id
            or reference.embedding_provider != self._embedding_provider
            or reference.index_version != self._versions.index
            or reference.chunk_count < 1
            or reference.embedding_dimension < 1
            or (
                self._expected_dimension
                and reference.embedding_dimension != self._expected_dimension
            )
        ):
            return False
        parsed = self._repository.parsed(reference.document_id, expected_parser)
        if parsed is None or (parsed.ocr_used and not parsed.source_latex.strip()):
            return False
        chunks = self._repository.chunks(reference.document_id, reference.chunker_fingerprint)
        if len(chunks) != reference.chunk_count:
            return False
        labels = self._repository.vector_labels(
            tuple(chunk.chunk_id for chunk in chunks),
            reference.embedding_model,
            reference.embedding_dimension,
            reference.index_version,
        )
        return (
            len(labels) == len(chunks)
            and all(indexed for _, indexed in labels.values())
            and self._vectors.contains_many(
                reference.embedding_model,
                reference.embedding_dimension,
                reference.index_version,
                tuple(label for label, _ in labels.values()),
            )
        )

    def _process(self, reference: Reference, content: bytes, *, force: bool) -> Reference:
        parser_fingerprint = self._versions.parser_fingerprint(ocr_used=reference.ocr_used)
        parsed = (
            None if force else self._repository.parsed(reference.document_id, parser_fingerprint)
        )
        if parsed is None and not force:
            alternate = self._versions.parser_fingerprint(ocr_used=not reference.ocr_used)
            parsed = self._repository.parsed(reference.document_id, alternate)
            if parsed is not None:
                parser_fingerprint = alternate
        if parsed is not None and parsed.ocr_used and not parsed.source_latex.strip():
            parsed = None
        if parsed is None:
            self._repository.save(replace(reference, status=ReferenceStatus.PARSING))
            parsed = self._parser.parse(content, reference.document_id)
            parser_fingerprint = self._versions.parser_fingerprint(ocr_used=parsed.ocr_used)
            self._repository.save_parsed(parsed, parser_fingerprint)
            self._events.info(
                "reference_parsed",
                document_id=reference.document_id,
                blocks=len(parsed.blocks),
                ocr=parsed.ocr_used,
            )
        else:
            self._events.info("reference_parse_reused", document_id=reference.document_id)
        self._repository.save(replace(reference, status=ReferenceStatus.CHUNKING))
        chunk_fingerprint = self._versions.chunker_fingerprint(parser_fingerprint)
        chunks = () if force else self._repository.chunks(reference.document_id, chunk_fingerprint)
        if not chunks:
            chunks = self._chunker.chunk(parsed, reference.title)
            if not chunks:
                raise ValidationError("Reference produced no semantic chunks")
            self._repository.save_chunks(chunks, chunk_fingerprint)
            self._events.info(
                "reference_chunked", document_id=reference.document_id, chunks=len(chunks)
            )
        else:
            self._events.info(
                "reference_chunks_reused", document_id=reference.document_id, chunks=len(chunks)
            )
        self._repository.save(replace(reference, status=ReferenceStatus.EMBEDDING))
        dimension = self._repository.vector_dimension(
            tuple(chunk.chunk_id for chunk in chunks),
            self._embedding.model_id,
            self._versions.index,
        ) or (
            reference.embedding_dimension
            if reference.embedding_model == self._embedding.model_id
            else 0
        )
        if self._expected_dimension and dimension != self._expected_dimension:
            dimension = self._expected_dimension
        for start in range(0, len(chunks), self._batch_size):
            batch = chunks[start : start + self._batch_size]
            dimension = self._index_batch(batch, dimension, force=force, all_chunks=chunks)
        self._repository.save(replace(reference, status=ReferenceStatus.INDEXING))
        labels = self._repository.vector_labels(
            tuple(chunk.chunk_id for chunk in chunks),
            self._embedding.model_id,
            dimension,
            self._versions.index,
        )
        if (
            len(labels) != len(chunks)
            or not all(indexed for _, indexed in labels.values())
            or not self._vectors.contains_many(
                self._embedding.model_id,
                dimension,
                self._versions.index,
                tuple(label for label, _ in labels.values()),
            )
        ):
            raise GenerationError("Reference vectors were not durably indexed")
        ready = replace(
            reference,
            status=ReferenceStatus.READY if reference.enabled else ReferenceStatus.DISABLED,
            enabled=reference.enabled,
            error="",
            parser_fingerprint=parser_fingerprint,
            ocr_used=parsed.ocr_used,
            chunker_fingerprint=chunk_fingerprint,
            embedding_model=self._embedding.model_id,
            embedding_provider=self._embedding_provider,
            embedding_dimension=dimension,
            index_version=self._versions.index,
            chunk_count=len(chunks),
        )
        self._repository.save(ready)
        stale = self._repository.prune_vectors(
            reference.document_id,
            tuple(chunk.chunk_id for chunk in chunks),
            self._embedding.model_id,
            dimension,
            self._versions.index,
        )
        for model, old_dimension, label, version in stale:
            self._vectors.remove(model, old_dimension, version, (label,))
        self._events.info("reference_ready", document_id=reference.document_id, chunks=len(chunks))
        return ready

    def _index_batch(
        self,
        batch: tuple[MathChunk, ...],
        dimension: int,
        *,
        force: bool,
        all_chunks: tuple[MathChunk, ...],
    ) -> int:
        model = self._embedding.model_id
        labels = (
            self._repository.vector_labels(
                tuple(chunk.chunk_id for chunk in batch), model, dimension, self._versions.index
            )
            if dimension
            else {}
        )
        missing = [
            chunk
            for chunk in batch
            if force
            or chunk.chunk_id not in labels
            or not labels[chunk.chunk_id][1]
            or not self._vectors.contains(
                model, dimension, self._versions.index, labels[chunk.chunk_id][0]
            )
        ]
        if not missing:
            self._events.info("reference_embedding_reused", count=len(batch))
            return dimension
        vectors = self._embedding.embed(tuple(chunk.embedding_text for chunk in missing))
        if len(vectors) != len(missing) or not vectors:
            raise GenerationError("Embedding provider returned an incomplete batch")
        vectors = self._contextualize_example_vectors(missing, vectors, all_chunks)
        actual_dimension = len(vectors[0])
        if (
            actual_dimension < 1
            or (self._expected_dimension and actual_dimension != self._expected_dimension)
            or (dimension and dimension != actual_dimension)
            or any(len(vector) != actual_dimension for vector in vectors)
        ):
            raise GenerationError("Embedding dimension changed within the reference collection")
        dimension = actual_dimension
        allocated = self._repository.allocate_labels(
            tuple(chunk.chunk_id for chunk in missing), model, dimension, self._versions.index
        )
        indexed = tuple(
            (allocated[chunk.chunk_id], vector)
            for chunk, vector in zip(missing, vectors, strict=True)
        )
        self._vectors.add(model, dimension, self._versions.index, indexed, replace_existing=force)
        self._repository.mark_indexed(tuple(label for label, _ in indexed))
        self._events.info(
            "reference_embedding_batch", count=len(indexed), model=model, dimension=dimension
        )
        return dimension

    def _contextualize_example_vectors(
        self,
        chunks: list[MathChunk],
        vectors: tuple[tuple[float, ...], ...],
        all_chunks: tuple[MathChunk, ...],
    ) -> tuple[tuple[float, ...], ...]:
        contextualizable = [
            (index, chunk)
            for index, chunk in enumerate(chunks)
            if chunk.block_type in {"example", "counterexample"}
            and chunk.relation == "example_of"
            and chunk.related_block_id
        ]
        if not contextualizable or self._example_context_alpha >= 1:
            return vectors
        by_block = {chunk.block_id: chunk for chunk in all_chunks}
        related_texts = tuple(
            by_block[chunk.related_block_id].embedding_text
            for _, chunk in contextualizable
            if chunk.related_block_id in by_block
        )
        if not related_texts:
            return vectors
        related_vectors = self._embedding.embed(related_texts)
        if len(related_vectors) != len(related_texts):
            raise GenerationError("Embedding provider returned incomplete related vectors")
        adjusted = list(vectors)
        alpha = self._example_context_alpha
        related_index = 0
        for vector_index, chunk in contextualizable:
            if chunk.related_block_id not in by_block:
                continue
            related = related_vectors[related_index]
            related_index += 1
            current = adjusted[vector_index]
            if len(current) != len(related):
                raise GenerationError("Related example embedding dimension mismatch")
            adjusted[vector_index] = tuple(
                alpha * y + (1 - alpha) * x for y, x in zip(current, related, strict=True)
            )
        return tuple(adjusted)

    def _required(self, document_id: str) -> Reference:
        reference = self._repository.get(document_id)
        if reference is None:
            raise ValidationError("Reference not found")
        return reference

    def list(self) -> tuple[Reference, ...]:
        with self._repository.transaction():
            return self._repository.list()

    def get(self, document_id: str) -> Reference:
        with self._repository.transaction():
            return self._required(document_id)

    def related_chunks(self, chunk_id: str) -> tuple[MathChunk, ...]:
        """Fetch linked proof/statement or exercise/solution only when requested."""
        with self._repository.transaction():
            return self._repository.related_chunks(chunk_id)

    def set_enabled(self, document_id: str, enabled: bool) -> Reference:
        with self._repository.transaction():
            reference = self._required(document_id)
            if enabled and not self._is_complete(reference):
                raise ValidationError("Reference is not fully indexed; reindex it first")
            status = ReferenceStatus.READY if enabled else ReferenceStatus.DISABLED
            updated = replace(reference, enabled=enabled, status=status)
            self._repository.save(updated)
            return updated

    def set_preferred(self, document_id: str, preferred: bool) -> Reference:
        with self._repository.transaction():
            updated = replace(self._required(document_id), preferred=preferred)
            self._repository.save(updated)
            return updated

    def remove(self, document_id: str) -> None:
        with self._repository.transaction():
            reference = self._required(document_id)
            labels = self._repository.all_labels(document_id)
            self._repository.remove(document_id)
            for model, dimension, label, version in labels:
                self._vectors.remove(model, dimension, version, (label,))
        self._files.remove(reference.content_hash)
        self._events.info("reference_removed", document_id=document_id)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: ReferenceFilters | None = None,
        purpose: str = "",
    ) -> ReferenceSearchResult:
        started = perf_counter()
        count = self._default_top_k if top_k is None else top_k
        if (
            not query.strip()
            or len(query) > MAX_REFERENCE_QUERY_CHARS
            or not 1 <= count <= self._max_top_k
        ):
            raise ValidationError("Query or top_k is outside allowed bounds")
        if purpose and purpose not in _PURPOSE_BLOCKS:
            raise ValidationError("Unsupported reference search purpose")
        filters = filters or ReferenceFilters()
        if purpose:
            filters = replace(filters, block_types=_PURPOSE_BLOCKS[purpose])
        with self._repository.transaction():
            if not self._repository.count_active():
                self._events.info(
                    "reference_search_empty", latency_ms=round((perf_counter() - started) * 1000)
                )
                return ReferenceSearchResult(SearchOutcome.EMPTY_LIBRARY, query=query)

        # Embedding can be a remote request.  Do not retain SQLite's writer lock
        # while awaiting it: a reference import must remain able to make progress.
        embedded_query = self._embedding.embed((query,))
        if len(embedded_query) != 1 or not embedded_query[0]:
            raise GenerationError("Embedding provider returned no query vector")
        query_vector = embedded_query[0]
        dimension = len(query_vector)
        with self._repository.transaction():
            labels = self._repository.eligible_labels(
                filters, self._embedding.model_id, dimension, self._versions.index
            )
            if not labels:
                self._events.info(
                    "reference_search_no_evidence",
                    reason="scope_empty",
                    latency_ms=round((perf_counter() - started) * 1000),
                )
                return ReferenceSearchResult(SearchOutcome.NO_RELEVANT_SOURCE, query=query)
            candidate_count = _candidate_count(count, self._max_top_k, query)
            candidates = self._vectors.search(
                self._embedding.model_id,
                dimension,
                self._versions.index,
                query_vector,
                labels,
                candidate_count,
            )
            records = self._repository.chunks_for_labels(tuple(label for label, _ in candidates))
        raw_hits = tuple(
            ReferenceHit(records[label][0], records[label][1], score)
            for label, score in candidates
            if label in records and score >= self._minimum_score
        )
        hits, eliminated = diversify_reference_hits(raw_hits, count)
        self._events.info(
            "reference_search",
            top_k=count,
            candidate_top_k=candidate_count,
            candidates=len(candidates),
            eligible_hits=len(raw_hits),
            retained=len(hits),
            eliminated_duplicates=tuple(hit.chunk.chunk_id for hit in eliminated),
            latency_ms=round((perf_counter() - started) * 1000),
        )
        if not hits:
            return ReferenceSearchResult(SearchOutcome.NO_RELEVANT_SOURCE, query=query)
        return ReferenceSearchResult(SearchOutcome.ENOUGH_EVIDENCE, hits, query)


def _candidate_count(requested: int, maximum: int, query: str) -> int:
    complexity_bonus = 2 if len(query.split()) > 24 else 0
    return min(maximum, max(requested, requested * 3 + complexity_bonus))


def diversify_reference_hits(
    hits: tuple[ReferenceHit, ...], requested: int
) -> tuple[tuple[ReferenceHit, ...], tuple[ReferenceHit, ...]]:
    retained: list[ReferenceHit] = []
    eliminated: list[ReferenceHit] = []
    seen_locations: set[tuple[str, int, int, str]] = set()
    seen_texts: list[set[str]] = []
    for hit in hits:
        fingerprint = (
            hit.chunk.document_id,
            hit.chunk.page_start,
            hit.chunk.page_end,
            hit.chunk.section,
        )
        tokens = _token_set(hit.chunk.content)
        duplicate_text = any(
            _jaccard(tokens, known) >= _DUPLICATE_TEXT_THRESHOLD for known in seen_texts
        )
        duplicate_location = fingerprint in seen_locations and len(retained) >= requested
        if duplicate_text or duplicate_location:
            eliminated.append(hit)
            continue
        retained.append(hit)
        seen_texts.append(tokens)
        seen_locations.add(fingerprint)
        if len(retained) >= requested:
            break
    return tuple(retained), tuple(eliminated)


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
