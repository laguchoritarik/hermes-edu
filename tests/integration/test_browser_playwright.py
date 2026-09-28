from __future__ import annotations

import contextlib
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from hermes_edu.application.use_cases.browser import BrowserService
from hermes_edu.browser.playwright import PlaywrightBrowserAdapter
from hermes_edu.domain.errors import HermesError


class IngestedDownloads:
    def __init__(self) -> None:
        self.imports: list[tuple[bytes, str]] = []

    def import_pdf_bytes(self, content: bytes, filename: str, *, title: str | None = None) -> str:
        self.imports.append((content, filename))
        return "doc-browser"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def local_site(root: Path):
    port = _free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_playwright_browser_local_fixture_workflow(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    ingestion = IngestedDownloads()
    service = BrowserService(
        PlaywrightBrowserAdapter(sessions_dir=tmp_path / "browser"),
        references=ingestion,
    )
    fixture_root = Path(__file__).parents[1] / "fixtures" / "browser_site"
    with local_site(fixture_root) as base_url:
        try:
            opened = service.open(f"{base_url}/index.html")
        except Exception as exc:
            pytest.skip(f"Chromium is not installed; run `playwright install chromium`: {exc}")
        assert opened.snapshot is not None
        assert opened.snapshot.title == "Hermes Browser Fixture"

        search_input = next(
            ref for ref in opened.snapshot.inputs if "Recherche" in ref.accessible_name
        )
        service.fill(search_input.id, "integrales")
        button = next(ref for ref in opened.snapshot.buttons if "Rechercher" in ref.accessible_name)
        clicked = service.click(element_id=button.id)
        assert clicked.snapshot is not None
        assert "Résultat visible" in clicked.snapshot.compact_text(max_chars=2000)

        service.scroll(direction="down", pixels=700)
        result_link = next(ref for ref in clicked.snapshot.links if "Ouvrir" in ref.accessible_name)
        original_tab = service.tabs().session.current_tab
        service.click(element_id=result_link.id)
        tabs = service.tabs().session.tabs
        assert len(tabs) >= 2

        back_to_original = service.switch_tab(original_tab)
        assert back_to_original.snapshot is not None
        downloaded = service.download(url=f"{base_url}/fixture.pdf")
        assert downloaded.download is not None
        assert downloaded.download.filename == "fixture.pdf"
        assert Path(downloaded.download.local_path).is_file()

        document_id = service.ingest_download(downloaded.download.id)
        assert document_id == "doc-browser"
        assert ingestion.imports == [
            (Path(downloaded.download.local_path).read_bytes(), "fixture.pdf")
        ]

        with contextlib.suppress(HermesError):
            service.close()
        service.shutdown()
