from __future__ import annotations

import pytest
from typer.testing import CliRunner

from hermes_edu.domain.models.chat import ChatResponse, ChatSession
from hermes_edu.interfaces.cli import chat as chat_cli
from hermes_edu.interfaces.cli.app import app


class FakeChatService:
    def __init__(self) -> None:
        self.session = ChatSession(
            "session-1",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        )
        self.messages: list[str] = []

    def start_session(self, project_id: str | None = None) -> ChatSession:
        return self.session

    def resume_session(self, session_id: str) -> ChatSession:
        return self.session

    def handle_message(self, session_id: str, message: str) -> ChatResponse:
        self.messages.append(message)
        return ChatResponse(
            "À bientôt." if message == "/exit" else "Compris.",
            self.session,
            should_exit=message == "/exit",
        )

    def handle_prompt(self, text: str, *, project_id: str | None = None) -> ChatResponse:
        self.messages.append(text)
        return ChatResponse("Pipeline appelé.", self.session)


def test_chat_command_starts_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeChatService()

    def fake_service(*, tex_only: bool = False, auto_confirm: bool = False) -> FakeChatService:
        return fake

    monkeypatch.setattr(chat_cli, "_service", fake_service)

    result = CliRunner().invoke(app, ["chat", "--new"], input="/exit\n")

    assert result.exit_code == 0, result.output
    assert "Hermes Edu" in result.output
    assert fake.messages == ["/exit"]


def test_prompt_command_uses_chat_service(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeChatService()

    def fake_service(*, tex_only: bool = False, auto_confirm: bool = False) -> FakeChatService:
        return fake

    monkeypatch.setattr(chat_cli, "_service", fake_service)

    result = CliRunner().invoke(app, ["prompt", "Prépare un cours sur les intégrales"])

    assert result.exit_code == 0, result.output
    assert fake.messages == ["Prépare un cours sur les intégrales"]
    assert "Pipeline appelé" in result.output
