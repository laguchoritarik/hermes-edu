"""MCP v2 exposure of stable local Hermes capabilities."""

import re
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from hermes_edu.bootstrap import (
    ReferenceLibraryChatAdapter,
    build_browser_service,
    build_knowledge,
    build_reference_library,
    repository_root,
)
from hermes_edu.config.paths import confined_path, resolved_path
from hermes_edu.config.settings import Settings, load_settings
from hermes_edu.documents.latex.pipeline import LatexDocumentAdapter, artifact_for_path
from hermes_edu.documents.latex.validator import validate_latex
from hermes_edu.domain.errors import HermesError, ValidationError
from hermes_edu.domain.models.browser import BrowserReadMode
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.reference import ReferenceFilters
from hermes_edu.interfaces.reference_results import (
    reference_chunk_payload,
    reference_search_payload,
)
from hermes_edu.knowledge.retrieval.vector import SQLiteVectorRetriever


def create_server(settings: Settings | None = None, *, root: Path | None = None) -> MCPServer:
    """Register allowlisted tools and public resources without exposing core internals."""
    config = settings or load_settings()
    base = root or repository_root()
    server = MCPServer("hermes-edu", version="0.1.0")

    cached_browser = None

    def browser_service():
        nonlocal cached_browser
        if cached_browser is not None:
            return cached_browser
        library = build_reference_library(config, root=base)
        cached_browser = build_browser_service(
            config,
            root=base,
            reference_ingestion=ReferenceLibraryChatAdapter(library),
        )
        return cached_browser

    @server.resource("curriculum://sample-mp/reduction", mime_type="text/markdown")
    def sample_curriculum() -> str:
        path = base / "examples" / "curriculum" / "math-mp-reduction.md"
        return path.read_text(encoding="utf-8")

    @server.resource("template://td/v1", mime_type="text/x-tex")
    def td_template() -> str:
        return files("hermes_edu.documents.templates").joinpath("td_v1.tex.j2").read_text()

    @server.tool()
    def search_knowledge(
        query: str, curriculum: str, track: str, kind: str = "curriculum", top_k: int = 5
    ) -> list[dict[str, str | float]]:
        """Search the local index with curriculum/track filters and source IDs."""
        if not query.strip() or len(query) > 500:
            raise ToolError("Query must contain 1-500 characters")
        if kind not in {"curriculum", "knowledge"} or not 1 <= top_k <= 20:
            raise ToolError("Invalid kind or top_k")
        try:
            store = build_knowledge(config, root=base)
            hits = SQLiteVectorRetriever(store, store.embedding).retrieve(
                query, LearningContext(curriculum, track), kind=kind, top_k=top_k
            )
        except HermesError as exc:
            raise ToolError(str(exc)) from exc
        return [
            {
                "chunk_id": hit.chunk_id,
                "text": hit.text,
                "source_id": hit.source.source_id,
                "title": hit.source.title,
                "location": hit.source.location,
                "score": hit.score,
            }
            for hit in hits
        ]

    @server.tool()
    def browser_open(url: str) -> dict[str, object]:
        """Open a URL with the generic browser tool and return a compact observation."""
        try:
            service = browser_service()
            observation = service.open(url)
            return {"observation": observation.compact_summary()}
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def browser_read(mode: str = "visible") -> dict[str, object]:
        try:
            if mode not in {"visible", "article", "full", "elements"}:
                raise ValidationError("Invalid browser read mode")
            service = browser_service()
            observation = service.read(BrowserReadMode(mode))
            return {"observation": observation.compact_summary()}
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def browser_click(element_id: str) -> dict[str, object]:
        try:
            service = browser_service()
            observation = service.click(element_id=element_id)
            return {"observation": observation.compact_summary()}
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def browser_fill(element_id: str, text: str) -> dict[str, object]:
        try:
            service = browser_service()
            observation = service.fill(element_id, text)
            return {"observation": observation.compact_summary()}
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def browser_scroll(direction: str = "down", pixels: int = 800) -> dict[str, object]:
        try:
            if direction not in {"up", "down"}:
                raise ValidationError("Invalid scroll direction")
            service = browser_service()
            observation = service.scroll(direction=direction, pixels=pixels)
            return {"observation": observation.compact_summary()}
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def browser_download(
        element_id: str = "", url: str = "", add_reference: bool = False
    ) -> dict[str, object]:
        try:
            service = browser_service()
            observation = service.download(element_id=element_id, url=url)
            payload: dict[str, object] = {"observation": observation.compact_summary()}
            if add_reference:
                if observation.download is None:
                    raise ValidationError("No browser download was captured")
                payload["document_id"] = service.ingest_download(observation.download.id)
            return payload
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def browser_screenshot(full_page: bool = False) -> dict[str, object]:
        try:
            service = browser_service()
            observation = service.screenshot(full_page=full_page)
            return {
                "observation": observation.compact_summary(),
                "path": observation.screenshot_path,
            }
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def add_reference(path: str, title: str = "") -> dict[str, object]:
        """Import one PDF under the configured data root."""
        try:
            return asdict(
                build_reference_library(config, root=base).import_pdf(
                    Path(path), title=title or None
                )
            )
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def add_references(paths: list[str]) -> list[dict[str, object]]:
        """Import several PDFs without exposing pipeline details."""
        try:
            return [
                asdict(reference)
                for reference in build_reference_library(config, root=base).import_many(
                    tuple(Path(path) for path in paths)
                )
            ]
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def import_reference_directory(directory: str) -> list[dict[str, object]]:
        """Import all PDFs from an allowlisted directory."""
        try:
            return [
                asdict(reference)
                for reference in build_reference_library(config, root=base).import_directory(
                    Path(directory)
                )
            ]
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def list_references() -> list[dict[str, object]]:
        try:
            return [
                asdict(reference) for reference in build_reference_library(config, root=base).list()
            ]
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def get_reference(document_id: str) -> dict[str, object]:
        try:
            return asdict(build_reference_library(config, root=base).get(document_id))
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def get_related_reference_chunks(chunk_id: str) -> list[dict[str, object]]:
        """Retrieve a proof, solution, or source statement linked to a hit."""
        try:
            return [
                reference_chunk_payload(chunk)
                for chunk in build_reference_library(config, root=base).related_chunks(chunk_id)
            ]
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def search_references(
        query: str,
        top_k: int | None = None,
        document_ids: list[str] | None = None,
        block_types: list[str] | None = None,
        chapter: str = "",
        section: str = "",
        preferred_only: bool = False,
        purpose: str = "",
    ) -> dict[str, object]:
        """Return bounded semantic evidence and an explicit empty/no-source outcome."""
        try:
            filters = ReferenceFilters(
                document_ids=tuple(document_ids or ()),
                block_types=tuple(block_types or ()),
                chapter=chapter,
                section=section,
                preferred_only=preferred_only,
            )
            return reference_search_payload(
                build_reference_library(config, root=base).search(
                    query, top_k=top_k, filters=filters, purpose=purpose
                )
            )
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def set_reference_enabled(document_id: str, enabled: bool) -> dict[str, object]:
        try:
            return asdict(
                build_reference_library(config, root=base).set_enabled(document_id, enabled)
            )
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def set_reference_preferred(document_id: str, preferred: bool) -> dict[str, object]:
        try:
            return asdict(
                build_reference_library(config, root=base).set_preferred(document_id, preferred)
            )
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def remove_reference(document_id: str) -> dict[str, str]:
        try:
            build_reference_library(config, root=base).remove(document_id)
            return {"removed": document_id}
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def reindex_reference(document_id: str) -> dict[str, object]:
        try:
            return asdict(build_reference_library(config, root=base).reindex(document_id))
        except HermesError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def validate_td_latex(source: str) -> str:
        """Validate a rendered TD LaTeX source without executing it."""
        try:
            validate_latex(source)
        except ValidationError as exc:
            raise ToolError(str(exc)) from exc
        return "valid"

    @server.tool()
    def compile_td_latex(thread_id: str) -> dict[str, str | int]:
        """Compile an existing workspace TD using fixed XeLaTeX options."""
        try:
            allowed = {root.strip() for root in config.hermes_mcp_allowed_roots.split(",")}
            if "workspace" not in allowed:
                raise ValidationError("Workspace compiler access is disabled by MCP allowlist")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", thread_id):
                raise ValidationError("Invalid thread ID")
            workspace = resolved_path(base, config.hermes_workspace_dir)
            tex_path = confined_path(workspace, workspace / thread_id / "td.tex")
            if not tex_path.is_file():
                raise ValidationError("Thread has no rendered td.tex")
            adapter = LatexDocumentAdapter(
                workspace,
                engine=config.hermes_latex_engine,
                timeout_seconds=config.hermes_latex_timeout_seconds,
            )
            artifact = adapter.compile(artifact_for_path(tex_path, "tex"))
            if artifact is None:
                raise ValidationError("PDF compilation is disabled")
        except HermesError as exc:
            raise ToolError(str(exc)) from exc
        return {"path": artifact.path, "sha256": artifact.sha256, "size_bytes": artifact.size_bytes}

    @server.prompt()
    def create_td(topic: str, curriculum: str = "sample-mp", track: str = "MP") -> str:
        """Reusable prompt for a bounded mathematics TD request."""
        return (
            f"Create a mathematics TD on {topic} for curriculum {curriculum}, track {track}. "
            "Use indexed curriculum sources, show a plan for approval, then provide exercises "
            "and solutions with citations."
        )

    return server


def main() -> None:
    """Run stdio transport without writing non-protocol output to stdout."""
    create_server().run("stdio")
