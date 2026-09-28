"""Application ports used by the reusable chat service."""

from pathlib import Path
from typing import Protocol

from hermes_edu.domain.models.chat import ChatSession, ProjectContext, TaskDraft
from hermes_edu.domain.models.reference import ReferenceSearchResult


class ChatSessionRepositoryPort(Protocol):
    def create(self, session: ChatSession) -> ChatSession:
        """Persist a new session."""
        ...

    def save(self, session: ChatSession) -> ChatSession:
        """Persist an existing session."""
        ...

    def get(self, session_id: str) -> ChatSession:
        """Load a session by id."""
        ...

    def last_id(self) -> str | None:
        """Return the most recently updated session id, if any."""
        ...


class ProjectContextPort(Protocol):
    def load(self, project_id: str | None) -> ProjectContext | None:
        """Load project defaults without prompting the user."""
        ...


class ChatReferencePort(Protocol):
    def add_pdf(self, path: Path) -> str:
        """Index or reuse a PDF and return its stable document id."""
        ...

    def describe(self, document_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Return compact labels for selected document ids."""
        ...

    def search(self, query: str, *, top_k: int | None = None) -> ReferenceSearchResult:
        """Search available references to check whether a task has enough evidence."""
        ...


class ChatTaskRunnerPort(Protocol):
    def run(self, session: ChatSession) -> ChatSession:
        """Execute the existing Hermes workflow represented by the draft."""
        ...

    def preview_plan(self, draft: TaskDraft) -> tuple[str, ...]:
        """Return an already known or deterministic lightweight plan preview."""
        ...
