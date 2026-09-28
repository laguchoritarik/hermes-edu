"""Provider-neutral browser session and page observation models."""

from dataclasses import dataclass, field
from enum import StrEnum

from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.chat import utc_now


def browser_now() -> str:
    return utc_now()


class BrowserActionRisk(StrEnum):
    READ_ONLY = "READ_ONLY"
    LOW = "LOW"
    CONSEQUENTIAL = "CONSEQUENTIAL"


class BrowserReadMode(StrEnum):
    VISIBLE = "visible"
    ARTICLE = "article"
    FULL = "full"
    ELEMENTS = "elements"


@dataclass(frozen=True, slots=True)
class BrowserViewport:
    width: int = 1280
    height: int = 900

    def __post_init__(self) -> None:
        if not 320 <= self.width <= 7680 or not 240 <= self.height <= 4320:
            raise ValidationError("Browser viewport dimensions are outside allowed bounds")


@dataclass(frozen=True, slots=True)
class BrowserElementRef:
    id: str
    role: str
    accessible_name: str = ""
    text: str = ""
    tag: str = ""
    visible: bool = True
    enabled: bool = True
    value: str = ""
    internal_locator: str = ""
    sensitive: bool = False

    def public_label(self) -> str:
        name = self.accessible_name or self.text or self.value
        if self.sensitive and self.value:
            name = "[redacted]"
        quoted = f' "{name[:120]}"' if name else ""
        return f"{self.id} [{self.role or self.tag}]{quoted}"


@dataclass(frozen=True, slots=True)
class BrowserForm:
    element_id: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowserTable:
    caption: str = ""
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class PageSnapshot:
    url: str
    title: str
    headings: tuple[str, ...] = ()
    text_blocks: tuple[str, ...] = ()
    links: tuple[BrowserElementRef, ...] = ()
    buttons: tuple[BrowserElementRef, ...] = ()
    forms: tuple[BrowserForm, ...] = ()
    inputs: tuple[BrowserElementRef, ...] = ()
    selects: tuple[BrowserElementRef, ...] = ()
    tables: tuple[BrowserTable, ...] = ()
    visible_elements: tuple[BrowserElementRef, ...] = ()
    status: int | None = None
    truncated: bool = False

    @property
    def interactive_elements(self) -> tuple[BrowserElementRef, ...]:
        return self.visible_elements

    def compact_text(self, *, max_chars: int) -> str:
        text = "\n".join(block for block in self.text_blocks if block.strip()).strip()
        return text[:max_chars] + ("..." if len(text) > max_chars else "")


@dataclass(frozen=True, slots=True)
class DownloadedArtifact:
    id: str
    filename: str
    mime_type: str
    local_path: str
    source_url: str
    content_hash: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class BrowserSession:
    session_id: str
    current_url: str = ""
    current_tab: str = ""
    tabs: tuple[str, ...] = ()
    downloads: tuple[DownloadedArtifact, ...] = ()
    created_at: str = field(default_factory=utc_now)
    last_activity: str = field(default_factory=utc_now)
    headless: bool = True
    viewport: BrowserViewport = field(default_factory=BrowserViewport)
    step_count: int = 0


@dataclass(frozen=True, slots=True)
class BrowserTrace:
    action_index: int
    action_type: str
    target: str
    url_before: str
    url_after: str
    success: bool
    duration_ms: int
    error: str = ""


@dataclass(frozen=True, slots=True)
class BrowserObservation:
    session: BrowserSession
    snapshot: PageSnapshot | None = None
    download: DownloadedArtifact | None = None
    screenshot_path: str = ""
    message: str = ""
    risk: BrowserActionRisk = BrowserActionRisk.LOW
    confirmation_required: bool = False
    trace: BrowserTrace | None = None

    def compact_summary(self, *, max_chars: int = 1200, max_elements: int = 30) -> str:
        lines = [f"URL: {self.session.current_url}"]
        if self.snapshot is not None:
            lines.append(f"Title: {self.snapshot.title}")
            visible = self.snapshot.compact_text(max_chars=max_chars)
            if visible:
                lines.extend(["Visible text:", visible])
            elements = self.snapshot.interactive_elements[:max_elements]
            if elements:
                lines.append("Interactive elements:")
                lines.extend(element.public_label() for element in elements)
        if self.download is not None:
            lines.append(f"Download: {self.download.filename} ({self.download.size_bytes} bytes)")
        if self.screenshot_path:
            lines.append(f"Screenshot: {self.screenshot_path}")
        if self.message:
            lines.append(self.message)
        return "\n".join(lines)

    def compact_text(self) -> str:
        """Compatibility alias for callers that expect a compact observation string."""
        return self.compact_summary()
