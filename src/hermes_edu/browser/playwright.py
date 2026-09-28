"""Playwright-backed BrowserPort adapter."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from hermes_edu.domain.errors import GenerationError, ValidationError
from hermes_edu.domain.models.browser import (
    BrowserElementRef,
    BrowserForm,
    BrowserObservation,
    BrowserReadMode,
    BrowserSession,
    BrowserViewport,
    DownloadedArtifact,
    PageSnapshot,
    browser_now,
)

_MAX_ELEMENTS = 80
_MAX_TEXT = 12000


class PlaywrightBrowserAdapter:
    """Chromium implementation; Playwright stays outside the core layers."""

    def __init__(self, *, sessions_dir: Path, max_snapshot_chars: int = _MAX_TEXT) -> None:
        self._sessions_dir = sessions_dir
        self._max_snapshot_chars = max_snapshot_chars
        self._playwright: Any | None = None
        self._browsers: dict[str, Any] = {}
        self._contexts: dict[str, Any] = {}
        self._pages: dict[str, Any] = {}
        self._active_page: dict[str, str] = {}
        self._sessions: dict[str, BrowserSession] = {}

    def create_session(self, *, headless: bool, viewport: BrowserViewport) -> BrowserSession:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise GenerationError(
                "Playwright is not installed. Install the `browser` extra and run "
                "`playwright install chromium`."
            ) from exc
        session_id = uuid4().hex
        session_dir = self._session_dir(session_id)
        (session_dir / "downloads").mkdir(parents=True, exist_ok=True)
        (session_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        playwright = self._playwright or sync_playwright().start()
        self._playwright = playwright
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": viewport.width, "height": viewport.height},
        )
        page = context.new_page()
        tab_id = uuid4().hex
        self._browsers[session_id] = browser
        self._contexts[session_id] = context
        self._pages[tab_id] = page
        self._active_page[session_id] = tab_id
        session = BrowserSession(
            session_id=session_id,
            current_tab=tab_id,
            tabs=(tab_id,),
            headless=headless,
            viewport=viewport,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> BrowserSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValidationError("Unknown browser session")
        return session

    def open(self, session_id: str, url: str) -> BrowserObservation:
        return self.navigate(session_id, url)

    def navigate(self, session_id: str, url: str) -> BrowserObservation:
        page = self._page(session_id)
        response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return self._observation(session_id, status=response.status if response else None)

    def read(self, session_id: str, *, mode: BrowserReadMode) -> BrowserObservation:
        return self._observation(session_id, mode=mode)

    def click(self, session_id: str, *, element_id: str = "", text: str = "") -> BrowserObservation:
        context = self._context(session_id)
        before = set(context.pages)
        locator = self._locator(session_id, element_id, text)
        try:
            with self._page(session_id).expect_popup(timeout=1000) as popup_info:
                locator.click(timeout=5000)
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            locator.click(timeout=5000)
        self._page(session_id).wait_for_timeout(100)
        self._detect_tabs(session_id, before)
        return self._observation(session_id)

    def type(self, session_id: str, element_id: str, text: str) -> BrowserObservation:
        self._locator(session_id, element_id, "").type(text, delay=20, timeout=5000)
        return self._observation(session_id)

    def fill(self, session_id: str, element_id: str, text: str) -> BrowserObservation:
        self._locator(session_id, element_id, "").fill(text, timeout=5000)
        return self._observation(session_id)

    def scroll(
        self,
        session_id: str,
        *,
        direction: str = "down",
        pixels: int = 800,
        element_id: str = "",
    ) -> BrowserObservation:
        if element_id:
            self._locator(session_id, element_id, "").scroll_into_view_if_needed(timeout=5000)
        else:
            distance = -abs(pixels) if direction == "up" else abs(pixels)
            self._page(session_id).mouse.wheel(0, distance)
        self._page(session_id).wait_for_timeout(100)
        return self._observation(session_id)

    def select(self, session_id: str, element_id: str, value: str) -> BrowserObservation:
        self._locator(session_id, element_id, "").select_option(value=value, timeout=5000)
        return self._observation(session_id)

    def check(
        self, session_id: str, element_id: str, *, checked: bool = True
    ) -> BrowserObservation:
        locator = self._locator(session_id, element_id, "")
        if checked:
            locator.check(timeout=5000)
        else:
            locator.uncheck(timeout=5000)
        return self._observation(session_id)

    def press(self, session_id: str, key: str) -> BrowserObservation:
        self._page(session_id).keyboard.press(key)
        return self._observation(session_id)

    def wait(
        self,
        session_id: str,
        *,
        element_id: str = "",
        text: str = "",
        timeout_ms: int = 5000,
    ) -> BrowserObservation:
        if element_id or text:
            self._locator(session_id, element_id, text).wait_for(timeout=timeout_ms)
        else:
            self._page(session_id).wait_for_load_state("networkidle", timeout=timeout_ms)
        return self._observation(session_id)

    def screenshot(
        self, session_id: str, *, full_page: bool = False, element_id: str = ""
    ) -> BrowserObservation:
        path = self._session_dir(session_id) / "screenshots" / f"{uuid4().hex}.png"
        if element_id:
            self._locator(session_id, element_id, "").screenshot(path=str(path), timeout=5000)
        else:
            self._page(session_id).screenshot(path=str(path), full_page=full_page, timeout=5000)
        return replace(self._observation(session_id), screenshot_path=str(path))

    def download(
        self, session_id: str, *, element_id: str = "", url: str = ""
    ) -> BrowserObservation:
        if url:
            return self._download_url(session_id, url)
        with self._page(session_id).expect_download(timeout=10000) as download_info:
            self._locator(session_id, element_id, "").click(timeout=5000)
        download = download_info.value
        temp_path = Path(download.path())
        target = self._session_dir(session_id) / "downloads" / download.suggested_filename
        temp_path.replace(target)
        return self._with_download(session_id, target, download.url)

    def back(self, session_id: str) -> BrowserObservation:
        self._page(session_id).go_back(wait_until="domcontentloaded", timeout=5000)
        return self._observation(session_id)

    def forward(self, session_id: str) -> BrowserObservation:
        self._page(session_id).go_forward(wait_until="domcontentloaded", timeout=5000)
        return self._observation(session_id)

    def reload(self, session_id: str) -> BrowserObservation:
        self._page(session_id).reload(wait_until="domcontentloaded", timeout=5000)
        return self._observation(session_id)

    def tabs(self, session_id: str) -> BrowserObservation:
        self._refresh_tabs(session_id)
        return BrowserObservation(self.get_session(session_id), message="Tabs refreshed")

    def switch_tab(self, session_id: str, tab_id: str) -> BrowserObservation:
        if tab_id not in self._pages:
            raise ValidationError("Unknown browser tab")
        self._active_page[session_id] = tab_id
        return self._observation(session_id)

    def close_tab(self, session_id: str, tab_id: str = "") -> BrowserObservation:
        target = tab_id or self.get_session(session_id).current_tab
        page = self._pages.pop(target, None)
        if page is not None:
            page.close()
        self._refresh_tabs(session_id)
        return BrowserObservation(self.get_session(session_id), message="Tab closed")

    def snapshot(self, session_id: str) -> PageSnapshot:
        return self._snapshot(session_id, BrowserReadMode.VISIBLE)

    def close(self, session_id: str) -> BrowserObservation:
        session = self.get_session(session_id)
        browser = self._browsers.pop(session_id, None)
        if browser is not None:
            browser.close()
        self._contexts.pop(session_id, None)
        for tab_id in session.tabs:
            self._pages.pop(tab_id, None)
        closed = replace(session, tabs=(), current_tab="", last_activity=browser_now())
        self._sessions[session_id] = closed
        return BrowserObservation(closed, message="Browser closed")

    def shutdown(self) -> None:
        for browser in tuple(self._browsers.values()):
            browser.close()
        self._browsers.clear()
        self._contexts.clear()
        self._pages.clear()
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _download_url(self, session_id: str, url: str) -> BrowserObservation:
        response = self._context(session_id).request.get(url, timeout=10000)
        if not response.ok:
            raise GenerationError(f"Download failed with HTTP {response.status}")
        filename = Path(url.split("?", 1)[0]).name or f"{uuid4().hex}.download"
        target = self._session_dir(session_id) / "downloads" / filename
        target.write_bytes(response.body())
        return self._with_download(session_id, target, url)

    def _with_download(self, session_id: str, path: Path, source_url: str) -> BrowserObservation:
        content = path.read_bytes()
        artifact = DownloadedArtifact(
            id=uuid4().hex,
            filename=path.name,
            mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            local_path=str(path),
            source_url=source_url,
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )
        session = replace(
            self.get_session(session_id),
            downloads=(*self.get_session(session_id).downloads, artifact),
            last_activity=browser_now(),
        )
        self._sessions[session_id] = session
        return replace(self._observation(session_id), session=session, download=artifact)

    def _observation(
        self,
        session_id: str,
        *,
        status: int | None = None,
        mode: BrowserReadMode = BrowserReadMode.VISIBLE,
    ) -> BrowserObservation:
        snapshot = self._snapshot(session_id, mode, status=status)
        session = replace(
            self.get_session(session_id),
            current_url=snapshot.url,
            last_activity=browser_now(),
        )
        self._sessions[session_id] = session
        return BrowserObservation(session, snapshot)

    def _snapshot(
        self, session_id: str, mode: BrowserReadMode, *, status: int | None = None
    ) -> PageSnapshot:
        page = self._page(session_id)
        body_text = "" if mode is BrowserReadMode.ELEMENTS else self._text(page, mode)
        blocks = tuple(line.strip() for line in body_text.splitlines() if line.strip())[:40]
        refs = tuple(self._element_ref(raw) for raw in self._elements(page))
        return PageSnapshot(
            url=str(page.url),
            title=str(page.title()),
            headings=tuple(
                text.strip()
                for text in page.locator("h1,h2,h3").all_inner_texts()[:20]
                if text.strip()
            ),
            text_blocks=blocks,
            links=tuple(ref for ref in refs if ref.role == "link"),
            buttons=tuple(ref for ref in refs if ref.role == "button"),
            forms=(BrowserForm("document"),) if refs else (),
            inputs=tuple(ref for ref in refs if ref.role in {"input", "textarea", "checkbox"}),
            selects=tuple(ref for ref in refs if ref.role == "select"),
            visible_elements=refs,
            status=status,
            truncated=len(body_text) >= self._max_snapshot_chars,
        )

    def _text(self, page: Any, mode: BrowserReadMode) -> str:
        selector = "article, main, body" if mode is BrowserReadMode.ARTICLE else "body"
        text = page.locator(selector).first.inner_text(timeout=5000)
        return str(text)[: self._max_snapshot_chars]

    def _elements(self, page: Any) -> list[dict[str, object]]:
        script = """
        (max) => {
          const nodes = Array.from(document.querySelectorAll(
            'a,button,input,textarea,select,[role="button"],[role="link"]'
          ));
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden'
              && style.display !== 'none';
          };
          return nodes.filter(visible).slice(0, max).map((el, index) => {
            const id = `e${index + 1}`;
            el.setAttribute('data-hermes-id', id);
            const tag = el.tagName.toLowerCase();
            const type = (el.getAttribute('type') || '').toLowerCase();
            const role = el.getAttribute('role') || (tag === 'a' ? 'link'
              : tag === 'button' ? 'button'
              : tag === 'select' ? 'select'
              : tag === 'textarea' ? 'textarea'
              : type === 'checkbox' ? 'checkbox'
              : tag === 'input' ? 'input' : tag);
            const sensitive = type === 'password';
            const rawName = el.getAttribute('aria-label') || el.getAttribute('placeholder')
              || el.innerText || el.getAttribute('value') || el.getAttribute('name') || '';
            return {
              id, role, tag, sensitive,
              name: sensitive ? 'password field' : String(rawName).trim().slice(0, 160),
              text: sensitive ? '' : String(el.innerText || '').trim().slice(0, 160),
              value: sensitive ? '' : String(el.value || '').trim().slice(0, 160),
              visible: true,
              enabled: !el.disabled,
              selector: `[data-hermes-id="${id}"]`
            };
          });
        }
        """
        return cast(list[dict[str, object]], page.evaluate(script, _MAX_ELEMENTS))

    @staticmethod
    def _element_ref(raw: dict[str, object]) -> BrowserElementRef:
        return BrowserElementRef(
            id=str(raw.get("id", "")),
            role=str(raw.get("role", "")),
            accessible_name=str(raw.get("name", "")),
            text=str(raw.get("text", "")),
            tag=str(raw.get("tag", "")),
            visible=bool(raw.get("visible", True)),
            enabled=bool(raw.get("enabled", True)),
            value=str(raw.get("value", "")),
            internal_locator=str(raw.get("selector", "")),
            sensitive=bool(raw.get("sensitive", False)),
        )

    def _locator(self, session_id: str, element_id: str, text: str) -> Any:
        page = self._page(session_id)
        if element_id:
            selector = f'[data-hermes-id="{element_id}"]'
            if page.locator(selector).count() == 0:
                self._snapshot(session_id, BrowserReadMode.ELEMENTS)
            locator = page.locator(selector).first
            if locator.count() == 0:
                raise ValidationError(f"Browser element disappeared: {element_id}")
            return locator
        if text:
            return page.get_by_text(text, exact=False).first
        raise ValidationError("Browser action needs an element id or text")

    def _detect_tabs(self, session_id: str, before_pages: set[Any]) -> None:
        for page in self._context(session_id).pages:
            if page not in before_pages:
                tab_id = uuid4().hex
                self._pages[tab_id] = page
                self._active_page[session_id] = tab_id
        self._refresh_tabs(session_id)

    def _refresh_tabs(self, session_id: str) -> None:
        context = self._context(session_id)
        for page in context.pages:
            if page not in self._pages.values():
                self._pages[uuid4().hex] = page
        session = self.get_session(session_id)
        tabs = tuple(tab_id for tab_id, page in self._pages.items() if page in context.pages)
        active = self._active_page.get(session_id) or (tabs[0] if tabs else "")
        self._active_page[session_id] = active
        self._sessions[session_id] = replace(
            session,
            tabs=tabs,
            current_tab=active,
            current_url=str(self._page(session_id).url) if active else "",
            last_activity=browser_now(),
        )

    def _page(self, session_id: str) -> Any:
        tab_id = self.get_session(session_id).current_tab or self._active_page.get(session_id)
        if not tab_id or tab_id not in self._pages:
            raise ValidationError("Browser session has no active tab")
        return self._pages[tab_id]

    def _context(self, session_id: str) -> Any:
        context = self._contexts.get(session_id)
        if context is None:
            raise ValidationError("Unknown browser session")
        return context

    def _session_dir(self, session_id: str) -> Path:
        return self._sessions_dir / session_id
