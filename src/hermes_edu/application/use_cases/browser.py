"""Browser service and Hermes browser tool over a provider-neutral port."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from hermes_edu.application.ports.browser import BrowserDownloadedReferencePort, BrowserPort
from hermes_edu.application.services.tools import HermesTool
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.agent import AgentToolSpec
from hermes_edu.domain.models.browser import (
    BrowserActionRisk,
    BrowserObservation,
    BrowserReadMode,
    BrowserSession,
    BrowserTrace,
    BrowserViewport,
)


class BrowserService:
    """Coordinates browser policy, bounded steps and reference ingestion handoff."""

    def __init__(
        self,
        browser: BrowserPort,
        *,
        enabled: bool = True,
        headless: bool = True,
        viewport: BrowserViewport | None = None,
        allowed_domains: tuple[str, ...] = (),
        blocked_domains: tuple[str, ...] = (),
        max_steps: int = 50,
        max_snapshot_chars: int = 12000,
        downloads_enabled: bool = True,
        screenshots_enabled: bool = True,
        require_confirmation: bool = True,
        references: BrowserDownloadedReferencePort | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValidationError("browser.max_steps must be at least 1")
        self._browser = browser
        self._enabled = enabled
        self._headless = headless
        self._viewport = viewport or BrowserViewport()
        self._allowed_domains = allowed_domains
        self._blocked_domains = blocked_domains
        self._max_steps = max_steps
        self._max_snapshot_chars = max_snapshot_chars
        self._downloads_enabled = downloads_enabled
        self._screenshots_enabled = screenshots_enabled
        self._require_confirmation = require_confirmation
        self._references = references
        self._session_id = ""
        self._step_count = 0
        self._traces: list[BrowserTrace] = []

    @property
    def session_id(self) -> str:
        return self._ensure_session().session_id

    def traces(self) -> tuple[BrowserTrace, ...]:
        return tuple(self._traces)

    def open(self, url: str) -> BrowserObservation:
        self._check_url(url)
        return self._call("OPEN", url, lambda session_id: self._browser.open(session_id, url))

    def navigate(self, url: str) -> BrowserObservation:
        self._check_url(url)
        return self._call(
            "NAVIGATE", url, lambda session_id: self._browser.navigate(session_id, url)
        )

    def read(self, mode: BrowserReadMode = BrowserReadMode.VISIBLE) -> BrowserObservation:
        return self._call(
            "READ",
            mode.value,
            lambda session_id: self._browser.read(session_id, mode=mode),
            read_only=True,
        )

    def click(
        self,
        *,
        element_id: str = "",
        text: str = "",
        confirmed: bool = False,
        risk: BrowserActionRisk = BrowserActionRisk.LOW,
    ) -> BrowserObservation:
        if risk is BrowserActionRisk.CONSEQUENTIAL and self._require_confirmation and not confirmed:
            session = self._ensure_session()
            return BrowserObservation(
                session,
                message="Confirmation required before consequential browser action.",
                risk=risk,
                confirmation_required=True,
            )
        target = element_id or text
        return self._call(
            "CLICK",
            target,
            lambda session_id: self._browser.click(session_id, element_id=element_id, text=text),
        )

    def type(self, element_id: str, text: str) -> BrowserObservation:
        return self._call(
            "TYPE",
            _safe_target(element_id),
            lambda session_id: self._browser.type(session_id, element_id, text),
        )

    def fill(self, element_id: str, text: str) -> BrowserObservation:
        return self._call(
            "FILL",
            _safe_target(element_id),
            lambda session_id: self._browser.fill(session_id, element_id, text),
        )

    def scroll(
        self, *, direction: str = "down", pixels: int = 800, element_id: str = ""
    ) -> BrowserObservation:
        target = element_id or f"{direction}:{pixels}"
        return self._call(
            "SCROLL",
            target,
            lambda session_id: self._browser.scroll(
                session_id, direction=direction, pixels=pixels, element_id=element_id
            ),
            read_only=True,
        )

    def select(self, element_id: str, value: str) -> BrowserObservation:
        return self._call(
            "SELECT",
            element_id,
            lambda session_id: self._browser.select(session_id, element_id, value),
        )

    def check(self, element_id: str, *, checked: bool = True) -> BrowserObservation:
        action = "CHECK" if checked else "UNCHECK"
        return self._call(
            action,
            element_id,
            lambda session_id: self._browser.check(session_id, element_id, checked=checked),
        )

    def press(self, key: str) -> BrowserObservation:
        return self._call("PRESS", key, lambda session_id: self._browser.press(session_id, key))

    def wait(
        self, *, element_id: str = "", text: str = "", timeout_ms: int = 5000
    ) -> BrowserObservation:
        return self._call(
            "WAIT",
            element_id or text,
            lambda session_id: self._browser.wait(
                session_id, element_id=element_id, text=text, timeout_ms=timeout_ms
            ),
            read_only=True,
        )

    def screenshot(self, *, full_page: bool = False, element_id: str = "") -> BrowserObservation:
        if not self._screenshots_enabled:
            raise ValidationError("Browser screenshots are disabled")
        return self._call(
            "SCREENSHOT",
            element_id or ("full_page" if full_page else "viewport"),
            lambda session_id: self._browser.screenshot(
                session_id, full_page=full_page, element_id=element_id
            ),
            read_only=True,
        )

    def download(self, *, element_id: str = "", url: str = "") -> BrowserObservation:
        if not self._downloads_enabled:
            raise ValidationError("Browser downloads are disabled")
        if url:
            self._check_url(url)
        return self._call(
            "DOWNLOAD",
            element_id or url,
            lambda session_id: self._browser.download(session_id, element_id=element_id, url=url),
        )

    def ingest_download(self, download_id: str, *, title: str | None = None) -> str:
        if self._references is None:
            raise ValidationError("Reference ingestion is not configured for browser downloads")
        session = self._ensure_session()
        match = next(
            (artifact for artifact in session.downloads if artifact.id == download_id), None
        )
        if match is None:
            raise ValidationError("Downloaded artifact not found in browser session")
        if not match.filename.lower().endswith(".pdf") and match.mime_type != "application/pdf":
            raise ValidationError("Only PDF browser downloads can be added as references")
        content = Path(match.local_path).read_bytes()
        return self._references.import_pdf_bytes(content, match.filename, title=title)

    def back(self) -> BrowserObservation:
        return self._call(
            "BACK", "", lambda session_id: self._browser.back(session_id), read_only=True
        )

    def forward(self) -> BrowserObservation:
        return self._call(
            "FORWARD", "", lambda session_id: self._browser.forward(session_id), read_only=True
        )

    def reload(self) -> BrowserObservation:
        return self._call(
            "RELOAD", "", lambda session_id: self._browser.reload(session_id), read_only=True
        )

    def tabs(self) -> BrowserObservation:
        return self._call(
            "TABS", "", lambda session_id: self._browser.tabs(session_id), read_only=True
        )

    def switch_tab(self, tab_id: str) -> BrowserObservation:
        return self._call(
            "SWITCH_TAB",
            tab_id,
            lambda session_id: self._browser.switch_tab(session_id, tab_id),
            read_only=True,
        )

    def close_tab(self, tab_id: str = "") -> BrowserObservation:
        return self._call(
            "CLOSE_TAB", tab_id, lambda session_id: self._browser.close_tab(session_id, tab_id)
        )

    def get_url(self) -> str:
        return self._ensure_session().current_url

    def get_title(self) -> str:
        return self._browser.snapshot(self.session_id).title

    def close(self) -> BrowserObservation:
        return self._call("CLOSE", "", lambda session_id: self._browser.close(session_id))

    def shutdown(self) -> None:
        self._browser.shutdown()

    def _ensure_session(self) -> BrowserSession:
        if not self._enabled:
            raise ValidationError("Browser tool is disabled")
        if not self._session_id:
            session = self._browser.create_session(headless=self._headless, viewport=self._viewport)
            self._session_id = session.session_id
            return session
        return self._browser.get_session(self._session_id)

    def _call(
        self,
        action: str,
        target: str,
        operation: Callable[[str], BrowserObservation],
        *,
        read_only: bool = False,
    ) -> BrowserObservation:
        if self._step_count >= self._max_steps:
            raise ValidationError("Browser max_steps exceeded")
        session = self._ensure_session()
        url_before = session.current_url
        started = perf_counter()
        self._step_count += 1
        try:
            result = operation(session.session_id)
            result = self._trim(result)
            success = True
            error = ""
        except Exception as exc:
            success = False
            error = str(exc)[:300]
            current = self._browser.get_session(session.session_id)
            result = BrowserObservation(current, message=error)
        trace = BrowserTrace(
            len(self._traces) + 1,
            action,
            _safe_target(target),
            url_before,
            result.session.current_url,
            success,
            round((perf_counter() - started) * 1000),
            error,
        )
        self._traces.append(trace)
        result = replace(result, trace=trace)
        if not success:
            raise ValidationError(error)
        if read_only:
            return replace(result, risk=BrowserActionRisk.READ_ONLY)
        return result

    def _trim(self, observation: BrowserObservation) -> BrowserObservation:
        snapshot = observation.snapshot
        if snapshot is None:
            return observation
        total = 0
        blocks: list[str] = []
        truncated = snapshot.truncated
        for block in snapshot.text_blocks:
            remaining = self._max_snapshot_chars - total
            if remaining <= 0:
                truncated = True
                break
            blocks.append(block[:remaining])
            total += len(blocks[-1])
            if len(block) > remaining:
                truncated = True
                break
        return replace(
            observation, snapshot=replace(snapshot, text_blocks=tuple(blocks), truncated=truncated)
        )

    def _check_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https", "file"}:
            raise ValidationError("Browser URL scheme is not allowed")
        host = parsed.hostname or ""
        if not host and parsed.scheme != "file":
            raise ValidationError("Browser URL must include a hostname")
        if any(host == domain or host.endswith(f".{domain}") for domain in self._blocked_domains):
            raise ValidationError("Browser navigation blocked by blocked_domains")
        if (
            self._allowed_domains
            and host
            and not any(
                host == domain or host.endswith(f".{domain}") for domain in self._allowed_domains
            )
        ):
            raise ValidationError("Browser navigation outside allowed_domains")


class BrowserTool(HermesTool):
    """Structured Hermes tool facade for browser actions."""

    def __init__(self, service: BrowserService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "browser"

    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            "browser",
            "Open, read, navigate and download web pages through the policy-checked browser service.",
            {
                "open": "Open a URL",
                "read": "Read compact page observations",
                "click": "Click element IDs with confirmation policy",
                "download": "Download a linked file",
                "ingest_download": "Add a downloaded PDF to references",
            },
        )

    def execute(self, action: str, arguments: Mapping[str, object]) -> object:
        match action:
            case "open":
                return self._service.open(_str(arguments, "url"))
            case "navigate":
                return self._service.navigate(_str(arguments, "url"))
            case "read":
                return self._service.read(BrowserReadMode(_str(arguments, "mode", "visible")))
            case "click":
                return self._service.click(
                    element_id=_str(arguments, "element_id"),
                    text=_str(arguments, "text"),
                    confirmed=_bool(arguments, "confirmed"),
                    risk=BrowserActionRisk(_str(arguments, "risk", "LOW")),
                )
            case "type":
                return self._service.type(_str(arguments, "element_id"), _str(arguments, "text"))
            case "fill":
                return self._service.fill(_str(arguments, "element_id"), _str(arguments, "text"))
            case "scroll":
                return self._service.scroll(
                    direction=_str(arguments, "direction", "down"),
                    pixels=_int(arguments, "pixels", 800),
                    element_id=_str(arguments, "element_id"),
                )
            case "select":
                return self._service.select(_str(arguments, "element_id"), _str(arguments, "value"))
            case "check":
                return self._service.check(_str(arguments, "element_id"), checked=True)
            case "uncheck":
                return self._service.check(_str(arguments, "element_id"), checked=False)
            case "press":
                return self._service.press(_str(arguments, "key"))
            case "wait":
                return self._service.wait(
                    element_id=_str(arguments, "element_id"),
                    text=_str(arguments, "text"),
                    timeout_ms=_int(arguments, "timeout_ms", 5000),
                )
            case "screenshot":
                return self._service.screenshot(
                    full_page=_bool(arguments, "full_page"),
                    element_id=_str(arguments, "element_id"),
                )
            case "download":
                return self._service.download(
                    element_id=_str(arguments, "element_id"), url=_str(arguments, "url")
                )
            case "ingest_download":
                return self._service.ingest_download(
                    _str(arguments, "download_id"), title=_str(arguments, "title") or None
                )
            case "back":
                return self._service.back()
            case "forward":
                return self._service.forward()
            case "reload":
                return self._service.reload()
            case "tabs":
                return self._service.tabs()
            case "switch_tab":
                return self._service.switch_tab(_str(arguments, "tab_id"))
            case "close_tab":
                return self._service.close_tab(_str(arguments, "tab_id"))
            case "close":
                return self._service.close()
            case "get_url":
                return self._service.get_url()
            case "get_title":
                return self._service.get_title()
            case _:
                raise ValidationError(f"Unsupported browser action: {action}")


def _str(arguments: Mapping[str, object], key: str, default: str = "") -> str:
    value = arguments.get(key, default)
    return str(value) if value is not None else default


def _int(arguments: Mapping[str, object], key: str, default: int) -> int:
    value = arguments.get(key, default)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError as exc:
        raise ValidationError(f"{key} must be an integer") from exc


def _bool(arguments: Mapping[str, object], key: str) -> bool:
    value = arguments.get(key, False)
    return value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes", "oui"}


def _safe_target(target: str) -> str:
    lowered = target.lower()
    if "password" in lowered or "secret" in lowered or "token" in lowered:
        return "[redacted]"
    return target[:200]
