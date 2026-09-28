from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hermes_edu.application.ports.browser import BrowserPort
from hermes_edu.application.use_cases.browser import BrowserService, BrowserTool
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.browser import (
    BrowserActionRisk,
    BrowserElementRef,
    BrowserObservation,
    BrowserReadMode,
    BrowserSession,
    BrowserViewport,
    DownloadedArtifact,
    PageSnapshot,
)


class FakeBrowser(BrowserPort):
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.calls: list[str] = []
        self.session = BrowserSession("fake", current_tab="tab-1", tabs=("tab-1",))
        self.snapshot_value = PageSnapshot(
            "about:blank",
            "Blank",
            text_blocks=("Visible fixture text",),
            buttons=(BrowserElementRef("e2", "button", "Rechercher", tag="button"),),
            inputs=(BrowserElementRef("e1", "textbox", "Recherche", tag="input"),),
            selects=(BrowserElementRef("e3", "select", "Année", tag="select"),),
            visible_elements=(
                BrowserElementRef("e1", "textbox", "Recherche", tag="input"),
                BrowserElementRef("e2", "button", "Rechercher", tag="button"),
                BrowserElementRef("e3", "select", "Année", tag="select"),
            ),
        )

    def create_session(self, *, headless: bool, viewport: BrowserViewport) -> BrowserSession:
        self.calls.append(f"create:{headless}:{viewport.width}")
        self.session = replace(self.session, headless=headless, viewport=viewport)
        return self.session

    def get_session(self, session_id: str) -> BrowserSession:
        return self.session

    def open(self, session_id: str, url: str) -> BrowserObservation:
        self.calls.append(f"open:{url}")
        self.session = replace(self.session, current_url=url)
        self.snapshot_value = replace(self.snapshot_value, url=url, title="Fixture", status=200)
        return BrowserObservation(self.session, self.snapshot_value)

    def navigate(self, session_id: str, url: str) -> BrowserObservation:
        self.calls.append(f"navigate:{url}")
        return self.open(session_id, url)

    def read(self, session_id: str, *, mode: BrowserReadMode) -> BrowserObservation:
        self.calls.append(f"read:{mode.value}")
        return BrowserObservation(self.session, self.snapshot_value)

    def click(self, session_id: str, *, element_id: str = "", text: str = "") -> BrowserObservation:
        self.calls.append(f"click:{element_id or text}")
        self.snapshot_value = replace(
            self.snapshot_value,
            text_blocks=(*self.snapshot_value.text_blocks, "Résultat visible"),
        )
        return BrowserObservation(self.session, self.snapshot_value)

    def type(self, session_id: str, element_id: str, text: str) -> BrowserObservation:
        self.calls.append(f"type:{element_id}:{text}")
        return BrowserObservation(self.session, self.snapshot_value)

    def fill(self, session_id: str, element_id: str, text: str) -> BrowserObservation:
        self.calls.append(f"fill:{element_id}:{text}")
        return BrowserObservation(self.session, self.snapshot_value)

    def scroll(
        self,
        session_id: str,
        *,
        direction: str = "down",
        pixels: int = 800,
        element_id: str = "",
    ) -> BrowserObservation:
        self.calls.append(f"scroll:{direction}:{pixels}:{element_id}")
        return BrowserObservation(self.session, self.snapshot_value)

    def select(self, session_id: str, element_id: str, value: str) -> BrowserObservation:
        self.calls.append(f"select:{element_id}:{value}")
        return BrowserObservation(self.session, self.snapshot_value)

    def check(
        self, session_id: str, element_id: str, *, checked: bool = True
    ) -> BrowserObservation:
        self.calls.append(f"check:{element_id}:{checked}")
        return BrowserObservation(self.session, self.snapshot_value)

    def press(self, session_id: str, key: str) -> BrowserObservation:
        self.calls.append(f"press:{key}")
        return BrowserObservation(self.session, self.snapshot_value)

    def wait(
        self,
        session_id: str,
        *,
        element_id: str = "",
        text: str = "",
        timeout_ms: int = 5000,
    ) -> BrowserObservation:
        self.calls.append(f"wait:{element_id or text}:{timeout_ms}")
        return BrowserObservation(self.session, self.snapshot_value)

    def screenshot(
        self, session_id: str, *, full_page: bool = False, element_id: str = ""
    ) -> BrowserObservation:
        self.calls.append(f"screenshot:{full_page}:{element_id}")
        path = self.tmp_path / "shot.png"
        path.write_bytes(b"png")
        return BrowserObservation(self.session, self.snapshot_value, screenshot_path=str(path))

    def download(
        self, session_id: str, *, element_id: str = "", url: str = ""
    ) -> BrowserObservation:
        self.calls.append(f"download:{element_id or url}")
        path = self.tmp_path / "fixture.pdf"
        path.write_bytes(b"%PDF-fixture")
        artifact = DownloadedArtifact(
            "abc123",
            "fixture.pdf",
            "application/pdf",
            str(path),
            url,
            "abc123",
            path.stat().st_size,
        )
        self.session = replace(self.session, downloads=(artifact,))
        return BrowserObservation(self.session, self.snapshot_value, download=artifact)

    def back(self, session_id: str) -> BrowserObservation:
        self.calls.append("back")
        return BrowserObservation(self.session, self.snapshot_value)

    def forward(self, session_id: str) -> BrowserObservation:
        self.calls.append("forward")
        return BrowserObservation(self.session, self.snapshot_value)

    def reload(self, session_id: str) -> BrowserObservation:
        self.calls.append("reload")
        return BrowserObservation(self.session, self.snapshot_value)

    def tabs(self, session_id: str) -> BrowserObservation:
        self.calls.append("tabs")
        self.session = replace(self.session, tabs=("tab-1", "tab-2"))
        return BrowserObservation(self.session, self.snapshot_value)

    def switch_tab(self, session_id: str, tab_id: str) -> BrowserObservation:
        self.calls.append(f"switch:{tab_id}")
        self.session = replace(self.session, current_tab=tab_id)
        return BrowserObservation(self.session, self.snapshot_value)

    def close_tab(self, session_id: str, tab_id: str = "") -> BrowserObservation:
        self.calls.append(f"close-tab:{tab_id}")
        return BrowserObservation(self.session, self.snapshot_value)

    def snapshot(self, session_id: str) -> PageSnapshot:
        return self.snapshot_value

    def close(self, session_id: str) -> BrowserObservation:
        self.calls.append("close")
        return BrowserObservation(self.session, message="closed")

    def shutdown(self) -> None:
        self.calls.append("shutdown")


class FakeReferences:
    def __init__(self) -> None:
        self.imports: list[tuple[bytes, str]] = []

    def import_pdf_bytes(self, content: bytes, filename: str, *, title: str | None = None) -> str:
        self.imports.append((content, filename))
        return "doc-fixture"


def test_browser_service_reuses_session_and_exposes_core_actions(tmp_path: Path) -> None:
    fake = FakeBrowser(tmp_path)
    service = BrowserService(fake, headless=True, references=FakeReferences())

    opened = service.open("https://example.test")
    assert opened.snapshot is not None
    assert opened.snapshot.title == "Fixture"
    service.fill("e1", "intégrales")
    clicked = service.click(element_id="e2")
    service.scroll(direction="down", pixels=600)
    service.select("e3", "2026")
    service.tabs()

    assert clicked.snapshot is not None
    assert "Résultat visible" in clicked.snapshot.compact_text(max_chars=500)
    assert fake.calls.count("create:True:1280") == 1
    assert "fill:e1:intégrales" in fake.calls
    assert "select:e3:2026" in fake.calls


def test_download_can_be_handed_to_reference_pipeline(tmp_path: Path) -> None:
    references = FakeReferences()
    service = BrowserService(FakeBrowser(tmp_path), references=references)

    downloaded = service.download(url="https://example.test/fixture.pdf")
    assert downloaded.download is not None
    assert service.ingest_download(downloaded.download.id) == "doc-fixture"
    assert references.imports == [(b"%PDF-fixture", "fixture.pdf")]


def test_screenshot_and_timeout_like_wait_are_traced(tmp_path: Path) -> None:
    service = BrowserService(FakeBrowser(tmp_path))
    service.open("https://example.test")
    shot = service.screenshot(full_page=True)
    service.wait(text="Ready", timeout_ms=100)

    assert shot.screenshot_path.endswith("shot.png")
    assert [trace.action_type for trace in service.traces()] == ["OPEN", "SCREENSHOT", "WAIT"]


def test_max_steps_and_domain_policy_are_enforced(tmp_path: Path) -> None:
    service = BrowserService(FakeBrowser(tmp_path), max_steps=1, blocked_domains=("blocked.test",))
    service.open("https://example.test")
    with pytest.raises(ValidationError, match="max_steps"):
        service.read()
    with pytest.raises(ValidationError, match="blocked_domains"):
        BrowserService(FakeBrowser(tmp_path), blocked_domains=("blocked.test",)).open(
            "https://blocked.test"
        )


def test_consequential_click_requires_confirmation(tmp_path: Path) -> None:
    service = BrowserService(FakeBrowser(tmp_path))

    observation = service.click(element_id="e2", risk=BrowserActionRisk.CONSEQUENTIAL)

    assert observation.confirmation_required
    assert (
        service.click(
            element_id="e2", risk=BrowserActionRisk.CONSEQUENTIAL, confirmed=True
        ).snapshot
        is not None
    )


def test_browser_tool_dispatches_without_importing_playwright(tmp_path: Path) -> None:
    fake = FakeBrowser(tmp_path)
    tool = BrowserTool(BrowserService(fake))

    result = tool.execute("open", {"url": "https://example.test"})

    assert isinstance(result, BrowserObservation)
    assert fake.calls[-1] == "open:https://example.test"


def test_secret_targets_are_redacted_from_trace(tmp_path: Path) -> None:
    service = BrowserService(FakeBrowser(tmp_path))

    service.open("https://example.test")
    service.fill("password-field", "super-secret")

    assert service.traces()[-1].target == "[redacted]"
