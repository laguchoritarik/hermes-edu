"""Embedding contract for local indexing and lookup."""

from typing import Protocol


class EmbeddingPort(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...
