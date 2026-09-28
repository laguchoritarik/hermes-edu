from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hermes_edu.application.ports.browser import BrowserPort
from hermes_edu.application.use_cases.browser import BrowserService, BrowserTool
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.browser import (
    BrowserElementRef,
    BrowserObservation,
    BrowserReadMode,
    BrowserSession,
    BrowserViewport,
    DownloadedArtifact,
    PageSnapshot,
)


class FakeBrowserPort(BrowserPort):
    def __init__(self) -> None:
        self.session = BrowserSession("browser-session", current_tab="tab-1", tabs=("tab-1",))
        self.actions: list[str] = []
        self.fail_next = ""

    def create_session(self, *, headless: bool, viewport: BrowserViewport) -> BrowserSession:
        self.session = replace(self.session, headless=headless, viewport=viewport)
        return self.session

    def get_session(self, session_id: str) -> BrowserSession:
        return self.session

    def open(self, session_id: str, url: str) -> BrowserObservation:
        self.actions.append(f"open:{url}")
        self.session = replace(self.session, current_url=url)
        return BrowserObservation(self.session, self.snapshot(session_id))

    def navigate(self, session_id: str, url: str) -> BrowserObservation:
        return self.open(session_id, url)

    def read(self, session_id: str, *, mode: BrowserReadMode) -> BrowserObservation:
        self.actions.append(f"read:{mode.value}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def click(self, session_id: str, *, element_id: str = "", text: str = "") -> BrowserObservation:
        self.actions.append(f"click:{element_id or text}")
        if self.fail_next:
            message = self.fail_next
            self.fail_next = ""
            raise RuntimeError(message)
        if element_id == "e4":
            self.session = replace(
                self.session,
                current_tab="tab-2",
                tabs=("tab-1", "tab-2"),
                current_url="https://local/result",
            )
        return BrowserObservation(self.session, self.snapshot(session_id))

    def type(self, session_id: str, element_id: str, text: str) -> BrowserObservation:
        self.actions.append(f"type:{element_id}:{text}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def fill(self, session_id: str, element_id: str, text: str) -> BrowserObservation:
        self.actions.append(f"fill:{element_id}:{text}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def scroll(
        self, session_id: str, *, direction: str = "down", pixels: int = 800, element_id: str = ""
    ) -> BrowserObservation:
        self.actions.append(f"scroll:{direction}:{pixels}:{element_id}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def select(self, session_id: str, element_id: str, value: str) -> BrowserObservation:
        self.actions.append(f"select:{element_id}:{value}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def check(
        self, session_id: str, element_id: str, *, checked: bool = True
    ) -> BrowserObservation:
        self.actions.append(f"check:{element_id}:{checked}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def press(self, session_id: str, key: str) -> BrowserObservation:
        self.actions.append(f"press:{key}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def wait(
        self, session_id: str, *, element_id: str = "", text: str = "", timeout_ms: int = 5000
    ) -> BrowserObservation:
        self.actions.append(f"wait:{element_id or text}:{timeout_ms}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def screenshot(
        self, session_id: str, *, full_page: bool = False, element_id: str = ""
    ) -> BrowserObservation:
        self.actions.append("screenshot")
        return BrowserObservation(
            self.session, self.snapshot(session_id), screenshot_path="/tmp/s.png"
        )

    def download(
        self, session_id: str, *, element_id: str = "", url: str = ""
    ) -> BrowserObservation:
        self.actions.append(f"download:{element_id or url}")
        artifact = DownloadedArtifact(
            "download-1",
            "fixture.pdf",
            "application/pdf",
            "/tmp/fixture.pdf",
            "https://local/fixture.pdf",
            "a" * 64,
            12,
        )
        self.session = replace(self.session, downloads=(artifact,))
        return BrowserObservation(self.session, self.snapshot(session_id), download=artifact)

    def back(self, session_id: str) -> BrowserObservation:
        self.actions.append("back")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def forward(self, session_id: str) -> BrowserObservation:
        self.actions.append("forward")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def reload(self, session_id: str) -> BrowserObservation:
        self.actions.append("reload")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def tabs(self, session_id: str) -> BrowserObservation:
        self.actions.append("tabs")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def switch_tab(self, session_id: str, tab_id: str) -> BrowserObservation:
        self.actions.append(f"switch:{tab_id}")
        self.session = replace(self.session, current_tab=tab_id)
        return BrowserObservation(self.session, self.snapshot(session_id))

    def close_tab(self, session_id: str, tab_id: str = "") -> BrowserObservation:
        self.actions.append(f"close_tab:{tab_id}")
        return BrowserObservation(self.session, self.snapshot(session_id))

    def snapshot(self, session_id: str) -> PageSnapshot:
        return PageSnapshot(
            url=self.session.current_url or "https://local/",
            title="Fixture",
            headings=("Fixture",),
            text_blocks=("Visible fixture text",),
            buttons=(BrowserElementRef("e1", "button", "Search", tag="button"),),
            inputs=(
                BrowserElementRef("e2", "input", "Search query", tag="input"),
                BrowserElementRef("e-password", "input", "password", tag="input", sensitive=True),
            ),
            selects=(BrowserElementRef("e3", "select", "Year", tag="select"),),
            links=(BrowserElementRef("e4", "link", "Result", tag="a"),),
            visible_elements=(
                BrowserElementRef("e1", "button", "Search", tag="button"),
                BrowserElementRef("e2", "input", "Search query", tag="input"),
                BrowserElementRef("e3", "select", "Year", tag="select"),
                BrowserElementRef("e4", "link", "Result", tag="a"),
            ),
        )

    def close(self, session_id: str) -> BrowserObservation:
        self.actions.append("close")
        self.session = replace(self.session, tabs=())
        return BrowserObservation(self.session, message="closed")

    def shutdown(self) -> None:
        self.actions.append("shutdown")


class FakeDownloadedReferences:
    def __init__(self) -> None:
        self.hashes: set[str] = set()
        self.calls = 0

    def import_pdf_bytes(self, content: bytes, filename: str, *, title: str | None = None) -> str:
        self.calls += 1
        self.hashes.add(filename)
        return f"doc-{filename}"


def make_service(
    max_steps: int = 50,
) -> tuple[BrowserService, FakeBrowserPort, FakeDownloadedReferences]:
    port = FakeBrowserPort()
    references = FakeDownloadedReferences()
    service = BrowserService(port, max_steps=max_steps, references=references)
    return service, port, references


def test_browser_session_creation_and_close() -> None:
    service, port, _ = make_service()
    assert service.session_id == "browser-session"
    assert service.close().session.tabs == ()
    assert port.actions == ["close"]


def test_open_title_visible_text_and_button_identification() -> None:
    service, _, _ = make_service()
    observation = service.open("https://local/")
    assert observation.snapshot is not None
    assert observation.snapshot.title == "Fixture"
    assert "Visible fixture text" in observation.snapshot.compact_text(max_chars=100)
    assert observation.snapshot.buttons[0].id == "e1"


def test_click_fill_scroll_select_tab_download_screenshot_and_ingest(tmp_path: Path) -> None:
    Path("/tmp/fixture.pdf").write_bytes(b"%PDF-1.4 fixture")
    service, port, refs = make_service()
    service.open("https://local/")
    service.fill("e2", "integrales")
    service.click(element_id="e1")
    service.scroll(direction="down", pixels=500)
    service.select("e3", "2026")
    service.click(element_id="e4")
    download = service.download(element_id="e5")
    shot = service.screenshot()
    document_id = service.ingest_download("download-1")

    assert "fill:e2:integrales" in port.actions
    assert download.download is not None
    assert shot.screenshot_path == "/tmp/s.png"
    assert document_id == "doc-fixture.pdf"
    assert refs.calls == 1


def test_stale_element_and_timeout_errors_are_traced() -> None:
    service, port, _ = make_service()
    service.open("https://local/")
    port.fail_next = "stale element"
    try:
        service.click(element_id="e1")
    except ValidationError as exc:
        assert "stale element" in str(exc)
    assert not service.traces()[-1].success


def test_secret_filtering_max_steps_and_tool_port_dispatch() -> None:
    service, port, _ = make_service(max_steps=3)
    tool = BrowserTool(service)
    tool.execute("open", {"url": "https://local/"})
    tool.execute("fill", {"element_id": "e-password", "text": "secret"})
    tool.execute("read", {"mode": "visible"})

    try:
        tool.execute("scroll", {"direction": "down"})
    except ValidationError as exc:
        assert "max_steps" in str(exc)

    assert "secret" not in service.traces()[1].target
    assert "fill:e-password:secret" in port.actions


def test_browser_service_and_chat_do_not_import_playwright() -> None:
    browser_source = Path("src/hermes_edu/application/use_cases/browser.py").read_text()
    chat_source = Path("src/hermes_edu/application/use_cases/chat.py").read_text()
    assert "playwright" not in browser_source.lower()
    assert "playwright" not in chat_source.lower()
