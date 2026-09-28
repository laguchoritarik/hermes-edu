"""MCP v2 exposes bounded local capabilities through the core adapters."""

import asyncio
from pathlib import Path

import pymupdf
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from hermes_edu.bootstrap import build_knowledge
from hermes_edu.config.settings import Settings
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.knowledge.ingestion.base import load_document
from hermes_edu.mcp.server import create_server


def test_mcp_surface_and_validation(tmp_path: Path) -> None:
    asyncio.run(_assert_mcp_surface_and_validation(tmp_path))


async def _assert_mcp_surface_and_validation(tmp_path: Path) -> None:
    root = Path.cwd()
    settings = Settings(
        hermes_db_path=tmp_path / "knowledge.db", hermes_embedding_provider="deterministic"
    )
    document = load_document(
        root / "examples" / "curriculum" / "math-mp-reduction.md",
        allowed_root=root / "examples" / "curriculum",
        source_id="sample",
        title="Synthetic MP",
        license="CC0-1.0",
        context=LearningContext("sample-mp", "MP"),
        kind="curriculum",
    )
    assert document.source.location == "curriculum/math-mp-reduction.md"
    build_knowledge(settings, root=root).index(document)
    server = create_server(settings, root=root)
    names = {tool.name for tool in await server.list_tools()}
    assert names == {
        "search_knowledge",
        "validate_td_latex",
        "compile_td_latex",
        "add_reference",
        "add_references",
        "import_reference_directory",
        "list_references",
        "get_reference",
        "get_related_reference_chunks",
        "search_references",
        "set_reference_enabled",
        "set_reference_preferred",
        "remove_reference",
        "reindex_reference",
        "browser_open",
        "browser_read",
        "browser_click",
        "browser_fill",
        "browser_scroll",
        "browser_download",
        "browser_screenshot",
    }
    resources = {str(resource.uri) for resource in await server.list_resources()}
    assert "curriculum://sample-mp/reduction" in resources
    valid = await server.call_tool(
        "validate_td_latex",
        {"source": r"\documentclass{article}\begin{document}Hi\end{document}"},
    )
    assert isinstance(valid, CallToolResult)
    assert not valid.is_error
    search = await server.call_tool(
        "search_knowledge",
        {"query": "eigenvalues", "curriculum": "sample-mp", "track": "MP", "top_k": 1},
    )
    assert isinstance(search, CallToolResult)
    assert "sample" in str(search.structured_content)
    with pytest.raises(ToolError, match="Invalid thread ID"):
        await server.call_tool("compile_td_latex", {"thread_id": "../escape"})


def test_mcp_reference_import_search_and_related(tmp_path: Path) -> None:
    asyncio.run(_assert_mcp_reference_import_search_and_related(tmp_path))


async def _assert_mcp_reference_import_search_and_related(tmp_path: Path) -> None:
    path = tmp_path / "data" / "algebra.pdf"
    path.parent.mkdir()
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text(  # pyright: ignore[reportUnknownMemberType]
        (72, 72),
        "Théorème 1 Toute base est une famille libre et génératrice.\n"
        "Preuve Par définition une base possède les deux propriétés.",
    )
    pdf.save(path)  # pyright: ignore[reportUnknownMemberType]
    pdf.close()
    settings = Settings(
        hermes_data_dir=tmp_path / "data",
        hermes_db_path=tmp_path / "knowledge.db",
        hermes_reference_dir=tmp_path / "retained",
        hermes_reference_hnsw_dir=tmp_path / "hnsw",
        hermes_embedding_provider="deterministic",
        hermes_reference_min_score=-1,
        hermes_reference_pdf_mode="text",
    )
    server = create_server(settings, root=tmp_path)
    imported = await server.call_tool("add_reference", {"path": str(path)})
    assert isinstance(imported, CallToolResult)
    assert "READY" in str(imported.structured_content)
    searched = await server.call_tool(
        "search_references", {"query": "base libre", "top_k": 2, "purpose": "theorem"}
    )
    assert isinstance(searched, CallToolResult)
    assert "ENOUGH_EVIDENCE" in str(searched.structured_content)
    assert "embedding_text" not in str(searched.structured_content)
