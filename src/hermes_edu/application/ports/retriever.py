"""Bounded knowledge lookup contract."""

from typing import Protocol

from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.source import RetrievedChunk


class RetrieverPort(Protocol):
    def retrieve(
        self, query: str, context: LearningContext, *, kind: str, top_k: int
    ) -> tuple[RetrievedChunk, ...]: ...
