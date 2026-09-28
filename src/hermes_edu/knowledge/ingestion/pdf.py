"""Bounded PDF text extraction for local indexing."""

# PyMuPDF's page overloads are incomplete for strict static checking.
# pyright: reportUnknownMemberType=false

from pathlib import Path
from typing import cast

from hermes_edu.domain.errors import ValidationError


def extract_pdf_text(path: Path) -> str:
    try:
        import pymupdf
    except ImportError as exc:
        raise ValidationError("Install the rag extra to ingest PDFs") from exc
    try:
        with pymupdf.open(path) as pdf:
            if pdf.page_count > 50 or pdf.needs_pass:
                raise ValidationError("PDF must be unencrypted and at most 50 pages")
            return "\n".join(cast(str, page.get_text("text")) for page in pdf)
    except (RuntimeError, ValueError) as exc:
        raise ValidationError("PDF text extraction failed") from exc
