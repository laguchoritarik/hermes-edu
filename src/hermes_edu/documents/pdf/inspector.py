"""Basic verification of a compiled PDF artifact."""

# PyMuPDF's Document properties are not fully typed in the installed release.
# pyright: reportUnknownMemberType=false

import re
from pathlib import Path
from typing import cast

from hermes_edu.domain.errors import CompilationError

_SUSPICIOUS_RENDERED_TEXT = re.compile(
    r"(?:\\[A-Za-z]{2,}|[A-Za-z0-9]\_[A-Za-z0-9]|[A-Za-z0-9]\^\{?[A-Za-z0-9]|�)"
)


def inspect_pdf(path: Path) -> int:
    """Return a positive page count after checking the PDF container."""
    try:
        import pymupdf
    except ImportError as exc:
        raise CompilationError("Install the rag extra for PDF inspection") from exc
    try:
        with pymupdf.open(path) as pdf:
            page_count = cast(int, pdf.page_count)
            if not pdf.is_pdf or page_count < 1:
                raise CompilationError("Compiled artifact is not a non-empty PDF")
            extracted = "\n".join(cast(str, page.get_text("text")) for page in pdf)
            suspicious = _SUSPICIOUS_RENDERED_TEXT.search(extracted)
            if suspicious:
                raise CompilationError(
                    f"Compiled PDF contains suspicious raw math text: {suspicious.group(0)}"
                )
            return page_count
    except (RuntimeError, ValueError) as exc:
        raise CompilationError("Compiled PDF cannot be opened") from exc
