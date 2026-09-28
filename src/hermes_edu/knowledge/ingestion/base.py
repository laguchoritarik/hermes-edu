"""Constrained local file ingestion into normalized text."""

from pathlib import Path
from urllib.parse import urlparse

from hermes_edu.config.paths import confined_path
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.source import SourceReference
from hermes_edu.knowledge.models import NormalizedDocument

MAX_SOURCE_BYTES = 2_000_000


def load_document(
    path: Path,
    *,
    allowed_root: Path,
    source_id: str,
    title: str,
    license: str,
    context: LearningContext,
    kind: str,
    source_url: str | None = None,
) -> NormalizedDocument:
    """Load a supported local source without following paths outside the allowlist."""
    safe_path = confined_path(allowed_root, path)
    if not safe_path.is_file() or safe_path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValidationError("Source must be an existing file no larger than 2 MB")
    if kind not in {"curriculum", "knowledge"}:
        raise ValidationError("Source kind must be curriculum or knowledge")
    suffix = safe_path.suffix.lower()
    if suffix in {".md", ".txt", ".tex"}:
        text = safe_path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        from hermes_edu.knowledge.ingestion.pdf import extract_pdf_text

        text = extract_pdf_text(safe_path)
    else:
        raise ValidationError("Supported source types are .md, .txt, .tex and .pdf")
    if not text.strip():
        raise ValidationError("Source contains no extractable text")
    location = _source_location(safe_path, allowed_root, source_url)
    source = SourceReference(source_id, title, location, license)
    return NormalizedDocument(source, context, kind, text)


def _source_location(path: Path, allowed_root: Path, source_url: str | None) -> str:
    """Use a public source URL when supplied, otherwise retain portable local provenance."""
    if source_url is None:
        return (Path(allowed_root.name) / path.relative_to(allowed_root.resolve())).as_posix()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError("source_url must be an absolute http(s) URL")
    return source_url
