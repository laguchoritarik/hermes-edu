"""Small application-level tool registry shared by chat, CLI and MCP adapters."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.agent import AgentToolSpec


class HermesTool(Protocol):
    @property
    def name(self) -> str: ...
    def execute(self, action: str, arguments: Mapping[str, object]) -> object: ...


class DescribedHermesTool(HermesTool, Protocol):
    def spec(self) -> AgentToolSpec: ...


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    action: str
    arguments: Mapping[str, object]


class ToolRegistry:
    """Allowlisted dispatch for structured Hermes tools."""

    def __init__(self, tools: tuple[HermesTool, ...] = ()) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def register(self, tool: HermesTool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def specs(self) -> tuple[AgentToolSpec, ...]:
        specs: list[AgentToolSpec] = []
        for name in self.names():
            tool = self._tools[name]
            if hasattr(tool, "spec"):
                specs.append(tool.spec())  # type: ignore[attr-defined]
            else:
                specs.append(AgentToolSpec(name, f"Hermes tool {name}"))
        return tuple(specs)

    def discover(self, query: str, *, limit: int = 6) -> tuple[AgentToolSpec, ...]:
        terms = {term for term in query.lower().replace(".", " ").split() if term}
        scored: list[tuple[int, AgentToolSpec]] = []
        for spec in self.specs():
            haystack = " ".join((spec.name, spec.description, " ".join(spec.actions))).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, spec))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return tuple(spec for _, spec in scored[:limit])

    def execute(self, call: ToolCall) -> object:
        tool = self._tools.get(call.name)
        if tool is None:
            raise ValidationError(f"Unknown tool: {call.name}")
        return tool.execute(call.action, call.arguments)


class ToolRouter:
    """Select a compact tool subset for a conversational turn."""

    def __init__(self, registry: ToolRegistry, *, max_tools: int = 6) -> None:
        self._registry = registry
        self._max_tools = max_tools

    def select(
        self,
        message: str,
        *,
        recent_observations: Iterable[str] = (),
    ) -> tuple[AgentToolSpec, ...]:
        lowered = " ".join((message, *recent_observations)).lower()
        selected: list[AgentToolSpec] = []
        specs = {spec.name: spec for spec in self._registry.specs()}

        def add(name: str) -> None:
            if name in specs and specs[name] not in selected:
                selected.append(specs[name])

        if any(word in lowered for word in ("fichier", "file", "pdf", "fourier", "ensam")):
            add("files")
            add("documents")
            add("references")
        if any(
            word in lowered
            for word in ("parseval", "contient", "cherche dans", "référence", "reference")
        ):
            add("documents")
            add("references")
        if any(
            word in lowered
            for word in ("site", "internet", "web", "http", "ministère", "ministere")
        ):
            add("browser")
            add("documents")
            add("references")
        if any(
            word in lowered
            for word in ("cours", "td", "séance", "seance", "intégrale", "integrale")
        ):
            add("draft")
            add("delegate")
            add("references")
        add("tools")
        if not selected:
            add("draft")
            add("references")
        return tuple(selected[: self._max_tools])
