from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hermes_edu.application.ports.chat import (
    ChatReferencePort,
    ChatSessionRepositoryPort,
    ChatTaskRunnerPort,
    ProjectContextPort,
)
from hermes_edu.application.use_cases.chat import ChatService
from hermes_edu.domain.models.browser import BrowserObservation, BrowserSession, PageSnapshot
from hermes_edu.domain.models.chat import (
    ChatSession,
    ChatStatus,
    ProducedArtifact,
    ProjectContext,
    TaskDraft,
)
from hermes_edu.domain.models.reference import (
    MathChunk,
    ReferenceHit,
    ReferenceSearchResult,
    SearchOutcome,
)


class MemorySessions(ChatSessionRepositoryPort):
    def __init__(self) -> None:
        self.saved: dict[str, ChatSession] = {}
        self.last: str | None = None

    def create(self, session: ChatSession) -> ChatSession:
        return self.save(session)

    def save(self, session: ChatSession) -> ChatSession:
        self.saved[session.id] = session
        self.last = session.id
        return session

    def get(self, session_id: str) -> ChatSession:
        return self.saved[session_id]

    def last_id(self) -> str | None:
        return self.last


class Projects(ProjectContextPort):
    def load(self, project_id: str | None) -> ProjectContext | None:
        if project_id == "ensam-analyse1":
            return ProjectContext(
                project_id,
                institution="ENSAM",
                subject="Analyse 1",
                level="ENSAM CP1",
                curriculum=project_id,
                track="CP1",
            )
        return None


class References(ChatReferencePort):
    def __init__(self) -> None:
        self.added: list[Path] = []
        self.search_calls = 0
        self.outcome = SearchOutcome.ENOUGH_EVIDENCE

    def add_pdf(self, path: Path) -> str:
        self.added.append(path)
        return "doc-1"

    def describe(self, document_ids: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(f"{item} - Reference" for item in document_ids)

    def search(self, query: str, *, top_k: int | None = None) -> ReferenceSearchResult:
        self.search_calls += 1
        if self.outcome is not SearchOutcome.ENOUGH_EVIDENCE:
            return ReferenceSearchResult(self.outcome, query=query)
        chunk = MathChunk(
            "chunk-1",
            "doc-1",
            "block-1",
            "definition",
            f"Contenu sur {query}",
            f"Contenu sur {query}",
            1,
            1,
        )
        return ReferenceSearchResult(
            SearchOutcome.ENOUGH_EVIDENCE,
            (ReferenceHit(chunk, "Reference", 0.9),),
            query,
        )


class Runner(ChatTaskRunnerPort):
    def __init__(self) -> None:
        self.runs = 0
        self.plan_calls = 0

    def run(self, session: ChatSession) -> ChatSession:
        self.runs += 1
        return replace(
            session,
            status=ChatStatus.COMPLETED,
            produced_artifacts=(ProducedArtifact("workspace/chat/td.tex", "tex"),),
        )

    def preview_plan(self, draft: TaskDraft) -> tuple[str, ...]:
        self.plan_calls += 1
        return ("Primitives", "Intégrale définie") if draft.topic else ()


class ChatBrowser:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def open(self, url: str) -> BrowserObservation:
        self.opened.append(url)
        session = BrowserSession("browser", current_url=url)
        snapshot = PageSnapshot(url, "Browser Fixture", text_blocks=("Contenu navigateur",))
        return BrowserObservation(session, snapshot)


def service() -> tuple[ChatService, MemorySessions, References, Runner]:
    sessions = MemorySessions()
    references = References()
    runner = Runner()
    return (
        ChatService(sessions=sessions, projects=Projects(), references=references, runner=runner),
        sessions,
        references,
        runner,
    )


def test_multiturn_draft_is_enriched_without_losing_previous_fields() -> None:
    chat, _, _, _ = service()
    session = chat.start_session()
    response = chat.handle_message(session.id, "Je veux un cours sur les intégrales.")
    response = chat.handle_message(response.session.id, "Pour première année ENSAM.")
    response = chat.handle_message(response.session.id, "En quatre séances et fais aussi un TD.")

    draft = response.session.task_draft
    assert draft.topic == "Intégrales"
    assert draft.level == "ENSAM CP1"
    assert draft.duration.sessions == 4
    assert draft.outputs == ("course", "tutorial")


def test_add_and_remove_tutorial_output() -> None:
    chat, _, _, _ = service()
    session = chat.start_session()
    response = chat.handle_message(session.id, "Je veux un cours sur les intégrales.")
    response = chat.handle_message(response.session.id, "Ajoute aussi un TD.")
    assert "tutorial" in response.session.task_draft.outputs

    response = chat.handle_message(response.session.id, "Finalement enlève le TD.")
    assert "tutorial" not in response.session.task_draft.outputs
    assert "course" in response.session.task_draft.outputs


def test_project_context_prevents_reasking_known_subject() -> None:
    chat, _, _, _ = service()
    session = chat.start_session("ensam-analyse1")
    response = chat.handle_message(session.id, "Prépare le chapitre sur les intégrales.")

    assert response.session.task_draft.subject == "Analyse 1"
    assert response.session.task_draft.level == "ENSAM CP1"
    assert not response.session.pending_questions


def test_missing_required_information_produces_one_question() -> None:
    chat, _, _, _ = service()
    session = chat.start_session()
    response = chat.handle_message(session.id, "Prépare le devoir.")

    assert response.session.pending_questions == ("Pour quel module ou chapitre ?",)
    assert response.message == "Pour quel module ou chapitre ?"


def test_add_reference_uses_reference_port() -> None:
    chat, _, references, _ = service()
    session = chat.start_session()
    response = chat.handle_message(session.id, "/add /tmp/integrales.pdf")

    assert references.added == [Path("/tmp/integrales.pdf")]
    assert response.session.selected_sources == ("doc-1",)


def test_missing_reference_coverage_asks_for_source_instead_of_hallucinating() -> None:
    chat, _, references, runner = service()
    references.outcome = SearchOutcome.NO_RELEVANT_SOURCE
    session = chat.start_session()
    response = chat.handle_message(session.id, "Je veux un cours sur les intégrales.")

    assert response.session.status == ChatStatus.DRAFTING
    assert "référence" in response.message
    assert response.session.pending_questions == (response.message,)
    assert references.search_calls == 1
    assert runner.runs == 0


def test_status_and_cached_plan_do_not_run_task() -> None:
    chat, _, _, runner = service()
    session = chat.start_session()
    response = chat.handle_message(session.id, "Je veux un TD sur les intégrales.")
    status = chat.handle_message(response.session.id, "/status")
    plan = chat.handle_message(response.session.id, "/plan")
    second_plan = chat.handle_message(response.session.id, "/plan")

    assert "Intégrales" in status.message
    assert "Primitives" in plan.message
    assert "Primitives" in second_plan.message
    assert runner.runs == 0
    assert runner.plan_calls == 1


def test_saved_session_can_be_resumed() -> None:
    chat, sessions, _, _ = service()
    session = chat.start_session()
    response = chat.handle_message(session.id, "Je veux un TD sur les intégrales.")

    assert sessions.last_id() == response.session.id
    assert chat.resume_session("last").task_draft.topic == "Intégrales"


def test_provider_error_does_not_crash_interactive_service() -> None:
    class FailingRunner(Runner):
        def run(self, session: ChatSession) -> ChatSession:
            from hermes_edu.domain.errors import GenerationError

            raise GenerationError("provider unavailable")

    sessions = MemorySessions()
    chat = ChatService(
        sessions=sessions,
        projects=Projects(),
        references=References(),
        runner=FailingRunner(),
    )
    session = chat.start_session()
    response = chat.handle_message(session.id, "Je veux un TD sur les intégrales.")
    response = chat.handle_message(response.session.id, "/run")

    assert response.session.status == ChatStatus.ERROR
    assert "provider unavailable" in response.message


def test_quality_gate_blocker_keeps_session_unpublished() -> None:
    class BlockingRunner(Runner):
        def run(self, session: ChatSession) -> ChatSession:
            self.runs += 1
            return replace(session, status=ChatStatus.READY, produced_artifacts=())

    sessions = MemorySessions()
    references = References()
    runner = BlockingRunner()
    chat = ChatService(
        sessions=sessions,
        projects=Projects(),
        references=references,
        runner=runner,
    )
    session = chat.start_session()
    response = chat.handle_message(session.id, "Je veux un cours sur les intégrales.")
    response = chat.handle_message(response.session.id, "/run")

    assert response.session.status == ChatStatus.READY
    assert response.session.produced_artifacts == ()


def test_chat_routes_browser_command_to_injected_tool() -> None:
    sessions = MemorySessions()
    references = References()
    runner = Runner()
    browser = ChatBrowser()
    chat = ChatService(
        sessions=sessions,
        projects=Projects(),
        references=references,
        runner=runner,
        browser=browser,  # type: ignore[arg-type]
    )
    session = chat.start_session()

    response = chat.handle_message(session.id, "/browser open https://example.test")

    assert browser.opened == ["https://example.test"]
    assert "Browser Fixture" in response.message
