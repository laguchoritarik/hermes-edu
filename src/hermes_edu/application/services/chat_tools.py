"""Hermes tools used by the conversational helper agent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import cast

from hermes_edu.application.ports.chat import ChatReferencePort
from hermes_edu.application.services.tools import HermesTool, ToolRegistry
from hermes_edu.config.paths import confined_path, resolved_path
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.agent import AgentToolSpec
from hermes_edu.domain.models.reference import SearchOutcome


class FileSearchTool(HermesTool):
    """Bounded local file search constrained to configured roots."""

    def __init__(
        self, *, root: Path, allowed_roots: tuple[Path, ...], max_results: int = 8
    ) -> None:
        self._root = root.resolve()
        self._allowed_roots = tuple(resolved_path(self._root, item) for item in allowed_roots)
        self._max_results = max_results

    @property
    def name(self) -> str:
        return "files"

    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            "files",
            "Search or inspect local files inside allowed Hermes roots.",
            {"search": "Find files by name terms", "stat": "Return compact file metadata"},
        )

    def execute(self, action: str, arguments: Mapping[str, object]) -> object:
        if action == "search":
            return self._search(arguments)
        if action == "stat":
            path = self._safe_path(str(arguments.get("path", "")))
            return {"path": str(path), "name": path.name, "bytes": path.stat().st_size}
        raise ValidationError(f"Unsupported files action: {action}")

    def _search(self, arguments: Mapping[str, object]) -> dict[str, object]:
        query = str(arguments.get("query", "")).strip().lower()
        if not query:
            raise ValidationError("files.search requires a query")
        root_hint = str(arguments.get("root_hint", "")).strip().lower()
        extensions = _str_tuple(arguments.get("extensions")) or (".pdf", ".tex", ".md", ".txt")
        normalized_extensions = tuple(
            extension if extension.startswith(".") else f".{extension}" for extension in extensions
        )
        terms = tuple(term for term in query.replace("-", " ").split() if term)
        matches: list[dict[str, object]] = []
        for base in self._allowed_roots:
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if len(matches) >= self._max_results:
                    break
                if not path.is_file() or path.suffix.lower() not in normalized_extensions:
                    continue
                rel = (
                    str(path.relative_to(self._root))
                    if path.is_relative_to(self._root)
                    else str(path)
                )
                haystack = f"{path.name} {rel}".lower()
                if root_hint and root_hint not in haystack:
                    continue
                if all(term in haystack for term in terms):
                    matches.append(
                        {"id": f"f{len(matches) + 1}", "path": str(path), "name": path.name}
                    )
        return {"query": query, "matches": matches, "truncated": len(matches) >= self._max_results}

    def _safe_path(self, value: str) -> Path:
        if not value.strip():
            raise ValidationError("files.stat requires a path")
        candidate = Path(value)
        for root in self._allowed_roots:
            try:
                path = confined_path(
                    root, candidate if candidate.is_absolute() else self._root / candidate
                )
            except ValidationError:
                continue
            if path.exists():
                return path
        raise ValidationError("Path is outside allowed roots")


class ReferenceTool(HermesTool):
    """Search and add personal references through the existing library port."""

    def __init__(self, references: ChatReferencePort) -> None:
        self._references = references

    @property
    def name(self) -> str:
        return "references"

    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            "references",
            "Search or add indexed teaching references through the Hermes reference library.",
            {
                "search": "Semantic reference search",
                "add_pdf": "Index a PDF path",
                "describe": "Describe selected references",
            },
        )

    def execute(self, action: str, arguments: Mapping[str, object]) -> object:
        if action == "search":
            query = str(arguments.get("query", "")).strip()
            result = self._references.search(query, top_k=_int(arguments.get("top_k"), 5))
            return {
                "outcome": result.outcome.value,
                "query": result.query,
                "hits": tuple(
                    {
                        "id": f"r{index}",
                        "document_id": hit.chunk.document_id,
                        "chunk_id": hit.chunk.chunk_id,
                        "label": hit.document_title,
                        "score": hit.score,
                        "excerpt": hit.chunk.content[:400],
                    }
                    for index, hit in enumerate(result.hits, start=1)
                ),
            }
        if action == "add_pdf":
            return {"document_id": self._references.add_pdf(Path(str(arguments.get("path", ""))))}
        if action == "describe":
            return {"labels": self._references.describe(_str_tuple(arguments.get("document_ids")))}
        raise ValidationError(f"Unsupported references action: {action}")


class DocumentSearchTool(HermesTool):
    """Document-level search facade backed by the reference library."""

    def __init__(self, references: ChatReferencePort) -> None:
        self._references = references

    @property
    def name(self) -> str:
        return "documents"

    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            "documents",
            "Search already indexed documents for compact excerpts.",
            {"search": "Search document contents", "ingest": "Index a local PDF path"},
        )

    def execute(self, action: str, arguments: Mapping[str, object]) -> object:
        if action == "search":
            query = str(arguments.get("query", "")).strip()
            result = self._references.search(query, top_k=_int(arguments.get("top_k"), 5))
            return {
                "found": result.outcome is SearchOutcome.ENOUGH_EVIDENCE,
                "query": result.query,
                "matches": tuple(
                    {
                        "id": f"d{index}",
                        "document_id": hit.chunk.document_id,
                        "chunk_id": hit.chunk.chunk_id,
                        "page_start": hit.chunk.page_start,
                        "page_end": hit.chunk.page_end,
                        "excerpt": hit.chunk.content[:500],
                    }
                    for index, hit in enumerate(result.hits, start=1)
                ),
            }
        if action == "ingest":
            return {"document_id": self._references.add_pdf(Path(str(arguments.get("path", ""))))}
        raise ValidationError(f"Unsupported documents action: {action}")


class ToolDiscoveryTool(HermesTool):
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "tools"

    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            "tools",
            "Discover compact tool specs by intent query.",
            {"discover": "Find relevant Hermes tools"},
        )

    def execute(self, action: str, arguments: Mapping[str, object]) -> object:
        if action != "discover":
            raise ValidationError(f"Unsupported tools action: {action}")
        specs = self._registry.discover(str(arguments.get("query", "")))
        return {"tools": tuple(asdict(spec) for spec in specs)}


class DraftTool(HermesTool):
    @property
    def name(self) -> str:
        return "draft"

    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            "draft",
            "Update TaskDraft working memory through AgentDecision UPDATE_STATE patches.",
            {"patch": "Use UPDATE_STATE instead of executing this directly"},
        )

    def execute(self, action: str, arguments: Mapping[str, object]) -> object:
        raise ValidationError("TaskDraft updates must use AgentDecision UPDATE_STATE")


class DelegateTool(HermesTool):
    @property
    def name(self) -> str:
        return "delegate"

    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            "delegate",
            "Delegate ready work to existing Hermes generators, validators and quality gates.",
            {
                "generator": "Run the existing workflow",
                "validator": "Use configured validation workflow",
            },
        )

    def execute(self, action: str, arguments: Mapping[str, object]) -> object:
        raise ValidationError("Delegation must use AgentDecision DELEGATE")


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in cast("list[object] | tuple[object, ...]", value))
    return ()


def _int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default
