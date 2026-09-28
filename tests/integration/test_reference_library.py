"""Offline checks for durable semantic reference ingestion and HNSW search."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import httpx
import pymupdf
import pytest
from typer.testing import CliRunner

from hermes_edu.bootstrap import build_reference_library
from hermes_edu.config.settings import Settings
from hermes_edu.domain.errors import GenerationError, ValidationError
from hermes_edu.domain.models.reference import (
    MathBlock,
    ParsedReference,
    ReferenceFilters,
    SearchOutcome,
)
from hermes_edu.interfaces.cli import references as references_cli
from hermes_edu.interfaces.cli.app import app as cli_app
from hermes_edu.knowledge.chunking.semantic import MathSemanticChunker
from hermes_edu.knowledge.embeddings.base import DeterministicEmbedding
from hermes_edu.knowledge.ingestion.ocr import ILoveMyLatexOCR
from hermes_edu.knowledge.ingestion.structured_pdf import StructuredPDFParser
from hermes_edu.knowledge.stores.hnsw import HNSWReferenceIndex
from hermes_edu.persistence.repositories.sqlite import SQLiteReferenceRepository


class CountingParser(StructuredPDFParser):
    calls = 0

    def parse(self, content: bytes, document_id: str) -> ParsedReference:
        self.calls += 1
        return super().parse(content, document_id)


class CountingEmbedding(DeterministicEmbedding):
    def __init__(self, model: str = "test-model", *, fail_at: int = 0) -> None:
        self._model = model
        self.calls = 0
        self.batches = 0
        self.fail_at = fail_at

    @property
    def model_id(self) -> str:
        return self._model

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.batches += 1
        if self.fail_at and self.batches == self.fail_at:
            raise RuntimeError("synthetic embedding failure")
        self.calls += len(texts)
        return super().embed(texts)


class TransactionProbeEmbedding(DeterministicEmbedding):
    def __init__(self, database: Path) -> None:
        self._database = database
        self.write_succeeded = False

    @property
    def model_id(self) -> str:
        return "test-model"

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        with sqlite3.connect(self._database, timeout=0) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS embedding_probe (query TEXT NOT NULL)")
            connection.execute("INSERT INTO embedding_probe VALUES (?)", (texts[0],))
        self.write_succeeded = True
        return super().embed(texts)


class FakeOCR:
    version = "fake-ocr-v1"
    calls = 0

    def convert(self, pdf_bytes: bytes) -> str:
        self.calls += 1
        return (
            "\\section{Familles libres}\n"
            "\\begin{definition}[Base]\n"
            "Une base est une famille libre et génératrice: $u_{n+1}=2u_n+3$.\n"
            "\\end{definition}"
        )


def _pdf(path: Path, *, variant: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text(  # pyright: ignore[reportUnknownMemberType]
        (72, 72),
        "Chapitre 1 Espaces vectoriels\n"
        "Section 1 Familles libres\n"
        "Définition 1 Une famille libre de vecteurs est indépendante.\n"
        "Théorème 2 Toute famille libre peut être complétée en une base.\n"
        "Preuve On ajoute des vecteurs indépendants jusqu'à obtenir une base.\n"
        "Remarque 3 Une base engendre tout l'espace vectoriel.\n"
        "Exemple 4 Les vecteurs canoniques forment une base de R deux.\n"
        "Exercice 5 Déterminer une base du plan vectoriel.\n"
        f"Solution La base canonique convient. {variant}",
        fontsize=10,
    )
    pdf.save(path)  # pyright: ignore[reportUnknownMemberType]
    pdf.close()


def _settings(root: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "hermes_data_dir": root / "data",
        "hermes_db_path": root / "knowledge.db",
        "hermes_reference_dir": root / "retained",
        "hermes_reference_hnsw_dir": root / "hnsw",
        "hermes_reference_min_score": -1,
        "hermes_reference_embedding_batch_size": 2,
        "hermes_reference_default_top_k": 3,
        "hermes_reference_pdf_mode": "text",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_parser_and_math_chunker_preserve_objects_and_relations(tmp_path: Path) -> None:
    path = tmp_path / "reference.pdf"
    _pdf(path)
    parsed = StructuredPDFParser().parse(path.read_bytes(), "doc")
    types = [block.block_type for block in parsed.blocks]
    assert types == ["definition", "theorem", "proof", "remark", "example", "exercise", "solution"]
    theorem, proof = parsed.blocks[1:3]
    exercise, solution = parsed.blocks[-2:]
    assert (proof.relation, proof.related_block_id) == ("proof_of", theorem.block_id)
    assert (solution.relation, solution.related_block_id) == ("solution_of", exercise.block_id)
    assert all(block.page_start == block.page_end == 1 for block in parsed.blocks)
    chunks = MathSemanticChunker().chunk(parsed, "Algebra")
    assert len(chunks) == len(parsed.blocks)
    assert chunks[0].content == parsed.blocks[0].text
    assert "Chapter: 1 Espaces vectoriels" in chunks[0].embedding_text
    assert chunks[-1].relation == "solution_of"


def test_very_long_proof_splits_at_paragraphs_with_parent(tmp_path: Path) -> None:
    paragraphs = [f"Step {number} " + "vector " * 55 for number in range(4)]
    block = MathBlock("proof-1", "proof", "\n\n".join(paragraphs), 2, 3)
    chunks = MathSemanticChunker(soft_max_tokens=100, hard_max_tokens=120).chunk(
        ParsedReference("doc", (block,)), "Algebra"
    )
    assert len(chunks) > 1
    assert all(chunk.parent_id == "proof-1" for chunk in chunks)
    assert [chunk.part_number for chunk in chunks] == list(range(1, len(chunks) + 1))
    assert all(chunk.parts_count == len(chunks) for chunk in chunks)
    assert all(len(chunk.content.split()) <= 120 for chunk in chunks)


def test_ocr_only_for_scanned_pdf(tmp_path: Path) -> None:
    ocr = FakeOCR()
    parser = StructuredPDFParser(ocr)
    text_path = tmp_path / "text.pdf"
    _pdf(text_path)
    assert not parser.parse(text_path.read_bytes(), "text").ocr_used
    assert ocr.calls == 0
    scan_path = tmp_path / "scan.pdf"
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(scan_path)  # pyright: ignore[reportUnknownMemberType]
    pdf.close()
    parsed = parser.parse(scan_path.read_bytes(), "scan")
    assert parsed.ocr_used
    assert parsed.blocks[0].block_type == "definition"
    assert parsed.blocks[0].section == "Familles libres"
    assert "$u_{n+1}=2u_n+3$" in parsed.blocks[0].text
    assert ocr.calls == 1


def test_required_conversion_uses_latex_even_for_text_pdf(tmp_path: Path) -> None:
    path = tmp_path / "text.pdf"
    _pdf(path)
    converter = FakeOCR()
    parsed = StructuredPDFParser(converter, require_conversion=True).parse(path.read_bytes(), "doc")
    assert converter.calls == 1
    assert parsed.ocr_used
    assert parsed.source_latex.startswith(r"\section{Familles libres}")
    assert len(parsed.blocks) == 1
    assert "$u_{n+1}=2u_n+3$" in parsed.blocks[0].text
    with pytest.raises(ValidationError, match="ILOVEMYLATEX_API_KEY"):
        StructuredPDFParser(require_conversion=True).parse(path.read_bytes(), "doc")


def test_converted_latex_is_cached_across_restart_and_model_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "data" / "text.pdf"
    _pdf(path)
    converter = FakeOCR()

    def convert(_adapter: ILoveMyLatexOCR, content: bytes) -> str:
        return converter.convert(content)

    monkeypatch.setattr(ILoveMyLatexOCR, "convert", convert)
    settings = _settings(tmp_path, hermes_reference_pdf_mode="latex", ilovemylatex_api_key="test")
    library = build_reference_library(settings, root=tmp_path, embedding=CountingEmbedding())
    first = library.import_pdf(path)
    assert first.ocr_used and first.chunk_count == 1
    repository = SQLiteReferenceRepository(tmp_path / "knowledge.db")
    with repository.transaction():
        parsed = repository.parsed(first.document_id, first.parser_fingerprint)
    assert parsed is not None and parsed.source_latex

    no_key = settings.model_copy(update={"ilovemylatex_api_key": ""})
    reused_embedding = CountingEmbedding()
    restarted = build_reference_library(no_key, root=tmp_path, embedding=reused_embedding)
    assert restarted.import_pdf(path).document_id == first.document_id
    assert reused_embedding.calls == 0
    changed_model = build_reference_library(
        no_key, root=tmp_path, embedding=CountingEmbedding("v2")
    )
    assert changed_model.import_pdf(path).status.value == "READY"
    assert converter.calls == 1

    with repository.transaction():
        repository.save_parsed(replace(parsed, source_latex=""), first.parser_fingerprint)
    changed_model.import_pdf(path)
    assert converter.calls == 2


def test_new_latex_import_without_key_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "data" / "text.pdf"
    _pdf(path)
    settings = _settings(tmp_path, hermes_reference_pdf_mode="latex", ilovemylatex_api_key="")
    library = build_reference_library(settings, root=tmp_path, embedding=CountingEmbedding())
    with pytest.raises(GenerationError, match="ILOVEMYLATEX_API_KEY"):
        library.import_pdf(path)
    assert library.list()[0].status.value == "FAILED"


def test_latex_mode_invalidates_old_text_parse(tmp_path: Path) -> None:
    path = tmp_path / "data" / "text.pdf"
    _pdf(path)
    settings = _settings(tmp_path)
    first = build_reference_library(
        settings, root=tmp_path, embedding=CountingEmbedding()
    ).import_pdf(path)
    converter = FakeOCR()
    converted = build_reference_library(
        settings,
        root=tmp_path,
        embedding=CountingEmbedding(),
        parser=StructuredPDFParser(converter, require_conversion=True),
    ).import_pdf(path)
    assert converted.document_id == first.document_id
    assert converted.parser_fingerprint != first.parser_fingerprint
    assert converted.chunk_count == 1 and converter.calls == 1


def test_ilovemylatex_upload_poll_result_contract() -> None:
    requests_seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request.url.path)
        assert request.headers["X-API-Key"] == "test-key"
        if request.url.path.endswith("/upload"):
            assert request.headers["Content-Type"] == "application/pdf"
            assert request.headers["X-Filename"] == "reference.pdf"
            assert request.read() == b"%PDF-synthetic"
            return httpx.Response(200, json={"file_id": "synthetic"})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "completed"})
        return httpx.Response(200, text=r"\begin{theorem}A basis spans.\end{theorem}")

    client = httpx.Client(transport=httpx.MockTransport(respond))
    result = ILoveMyLatexOCR(
        api_key="test-key", base_url="https://example.test/api/v1", client=client
    ).convert(b"%PDF-synthetic")
    assert "basis spans" in result
    assert requests_seen == [
        "/api/v1/documents/upload",
        "/api/v1/documents/synthetic/status",
        "/api/v1/documents/synthetic/result",
    ]


def test_duplicate_rename_version_invalidation_and_model_change(tmp_path: Path) -> None:
    path = tmp_path / "data" / "reference.pdf"
    _pdf(path)
    parser = CountingParser()
    embedding = CountingEmbedding()
    library = build_reference_library(
        _settings(tmp_path), root=tmp_path, embedding=embedding, parser=parser
    )
    first = library.import_pdf(path)
    assert first.chunk_count == 7
    initial_embeddings = embedding.calls
    renamed = path.with_name("renamed.pdf")
    renamed.write_bytes(path.read_bytes())
    duplicate = library.import_pdf(renamed)
    assert duplicate.document_id == first.document_id
    assert parser.calls == 1 and embedding.calls == initial_embeddings
    assert len(library.list()) == 1

    changed_chunker = build_reference_library(
        _settings(tmp_path, hermes_reference_soft_max_tokens=900),
        root=tmp_path,
        embedding=embedding,
        parser=parser,
    )
    rechunked = changed_chunker.import_pdf(renamed)
    assert rechunked.document_id == first.document_id
    assert parser.calls == 1
    assert embedding.calls == initial_embeddings + rechunked.chunk_count + 1

    next_model = CountingEmbedding("new-model")
    changed_model = build_reference_library(
        _settings(tmp_path, hermes_reference_soft_max_tokens=900),
        root=tmp_path,
        embedding=next_model,
        parser=parser,
    )
    changed_model.import_pdf(renamed)
    assert parser.calls == 1
    assert next_model.calls == first.chunk_count + 1

    _pdf(path, variant="Changed content")
    changed_content = changed_model.import_pdf(path)
    assert changed_content.document_id != first.document_id
    assert len(changed_model.list()) == 2
    assert parser.calls == 2


def test_parser_version_change_reparses_and_rechunks(tmp_path: Path) -> None:
    path = tmp_path / "data" / "reference.pdf"
    _pdf(path)
    parser = CountingParser()
    embedding = CountingEmbedding()
    library = build_reference_library(
        _settings(tmp_path), root=tmp_path, parser=parser, embedding=embedding
    )
    first = library.import_pdf(path)
    parser.version = "pymupdf-math-blocks-v2"
    updated = build_reference_library(
        _settings(tmp_path), root=tmp_path, parser=parser, embedding=embedding
    ).import_pdf(path)
    assert parser.calls == 2
    assert updated.parser_fingerprint != first.parser_fingerprint
    assert updated.chunker_fingerprint != first.chunker_fingerprint
    assert updated.status.value == "READY"


def test_directory_restart_reindex_and_existing_schema(tmp_path: Path) -> None:
    database = tmp_path / "knowledge.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE legacy_td (name TEXT)")
        connection.execute("INSERT INTO legacy_td VALUES ('preserved')")
    folder = tmp_path / "data" / "books"
    first_path, second_path = folder / "first.pdf", folder / "second.pdf"
    _pdf(first_path)
    _pdf(second_path, variant="second")
    parser = CountingParser()
    embed = CountingEmbedding()
    library = build_reference_library(
        _settings(tmp_path), root=tmp_path, parser=parser, embedding=embed
    )
    imported = library.import_directory(folder)
    assert len(imported) == 2
    reloaded = build_reference_library(
        _settings(tmp_path), root=tmp_path, parser=parser, embedding=embed
    )
    reloaded.import_pdf(first_path)
    assert parser.calls == 2
    assert reloaded.search("base").hits
    forced = reloaded.reindex(imported[0].document_id)
    assert forced.status.value == "READY"
    assert parser.calls == 3
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM legacy_td").fetchone() == ("preserved",)


def test_hnsw_search_filters_relevance_and_delete(tmp_path: Path) -> None:
    path = tmp_path / "data" / "reference.pdf"
    _pdf(path)
    library = build_reference_library(
        _settings(tmp_path, hermes_reference_max_top_k=3),
        root=tmp_path,
        embedding=CountingEmbedding(),
    )
    assert library.search("base").outcome == SearchOutcome.EMPTY_LIBRARY
    reference = library.import_pdf(path)
    exercises = library.search("base", top_k=2, purpose="exercises")
    assert exercises.outcome == SearchOutcome.ENOUGH_EVIDENCE
    assert all(hit.chunk.block_type in {"exercise", "question"} for hit in exercises.hits)
    assert all(hit.chunk.document_id == reference.document_id for hit in exercises.hits)
    assert (
        library.search("base", filters=ReferenceFilters(preferred_only=True)).outcome
        == SearchOutcome.NO_RELEVANT_SOURCE
    )
    library.set_preferred(reference.document_id, True)
    assert library.search("base", filters=ReferenceFilters(preferred_only=True)).hits
    theorem = library.search("base", top_k=3, purpose="theorem").hits[0].chunk
    assert any(chunk.relation == "proof_of" for chunk in library.related_chunks(theorem.chunk_id))
    exercise = library.search("base", top_k=3, purpose="exercises").hits[0].chunk
    assert any(
        chunk.relation == "solution_of" for chunk in library.related_chunks(exercise.chunk_id)
    )
    assert (
        library.search("base", filters=ReferenceFilters(document_ids=("other",))).outcome
        == SearchOutcome.NO_RELEVANT_SOURCE
    )
    strict = build_reference_library(
        _settings(tmp_path, hermes_reference_max_top_k=3, hermes_reference_min_score=1),
        root=tmp_path,
        embedding=CountingEmbedding(),
    )
    assert strict.search("unrelated query").outcome == SearchOutcome.NO_RELEVANT_SOURCE
    with pytest.raises(ValidationError):
        library.search("base", top_k=4)
    library.set_enabled(reference.document_id, False)
    assert library.search("base").outcome == SearchOutcome.EMPTY_LIBRARY
    assert library.related_chunks(theorem.chunk_id) == ()
    assert not library.import_pdf(path).enabled
    library.set_enabled(reference.document_id, True)
    repository = SQLiteReferenceRepository(tmp_path / "knowledge.db")
    with repository.transaction():
        labels = repository.all_labels(reference.document_id)
    library.remove(reference.document_id)
    assert library.search("base").outcome == SearchOutcome.EMPTY_LIBRARY
    with repository.transaction():
        assert repository.all_labels(reference.document_id) == ()
    vectors = HNSWReferenceIndex(tmp_path / "hnsw")
    assert all(
        not vectors.contains(model, dimension, version, label)
        for model, dimension, label, version in labels
    )
    assert labels
    assert not (tmp_path / "retained" / f"{reference.content_hash}.pdf").exists()


def test_search_releases_database_writer_lock_before_query_embedding(tmp_path: Path) -> None:
    path = tmp_path / "data" / "reference.pdf"
    _pdf(path)
    settings = _settings(tmp_path)
    library = build_reference_library(settings, root=tmp_path, embedding=CountingEmbedding())
    library.import_pdf(path)
    probe = TransactionProbeEmbedding(tmp_path / "knowledge.db")
    searchable = build_reference_library(settings, root=tmp_path, embedding=probe)

    result = searchable.search("base")

    assert result.outcome == SearchOutcome.ENOUGH_EVIDENCE
    assert probe.write_succeeded
    with sqlite3.connect(tmp_path / "knowledge.db") as connection:
        assert connection.execute("SELECT query FROM embedding_probe").fetchone() == ("base",)


def test_failed_embedding_resumes_saved_parse_chunks_and_first_batch(tmp_path: Path) -> None:
    path = tmp_path / "data" / "reference.pdf"
    _pdf(path)
    parser = CountingParser()
    failing = CountingEmbedding(fail_at=2)
    library = build_reference_library(
        _settings(tmp_path), root=tmp_path, parser=parser, embedding=failing
    )
    with pytest.raises(GenerationError):
        library.import_pdf(path)
    assert library.list()[0].status.value == "FAILED"
    assert parser.calls == 1 and failing.calls == 2
    working = CountingEmbedding()
    resumed = build_reference_library(
        _settings(tmp_path), root=tmp_path, parser=parser, embedding=working
    )
    ready = resumed.import_pdf(path)
    assert ready.status.value == "READY"
    assert parser.calls == 1
    assert working.calls == ready.chunk_count - 2 + 1


def test_simultaneous_duplicate_import_has_one_parse(tmp_path: Path) -> None:
    path = tmp_path / "data" / "reference.pdf"
    _pdf(path)
    parser = CountingParser()

    def worker(_index: int) -> str:
        library = build_reference_library(
            _settings(tmp_path), root=tmp_path, parser=parser, embedding=CountingEmbedding()
        )
        return library.import_pdf(path).document_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = tuple(pool.map(worker, range(2)))
    assert ids[0] == ids[1]
    assert parser.calls == 1


def test_reference_cli_add_and_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "data" / "reference.pdf"
    _pdf(path)
    monkeypatch.setattr(references_cli, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(references_cli, "repository_root", lambda: tmp_path)
    runner = CliRunner()
    imported = runner.invoke(cli_app, ["references", "add", str(path)])
    assert imported.exit_code == 0, imported.output
    assert '"status": "READY"' in imported.output
    searched = runner.invoke(cli_app, ["references", "search", "base", "--top-k", "2"])
    assert searched.exit_code == 0, searched.output
    assert '"outcome": "ENOUGH_EVIDENCE"' in searched.output
