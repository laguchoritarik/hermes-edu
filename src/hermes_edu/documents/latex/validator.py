"""Static safety check for rendered TeX before invoking an engine."""

import re

from hermes_edu.domain.errors import ValidationError

FORBIDDEN = re.compile(
    r"\\(?:input|include|openout|read|write|catcode|csname|directlua|special|"
    r"includegraphics|immediate|pdfobj|pdfximage)\b|\\write18\b",
    re.IGNORECASE,
)


def validate_latex(source: str) -> None:
    if len(source) > 300_000:
        raise ValidationError("Rendered LaTeX exceeds the 300 KB limit")
    match = FORBIDDEN.search(source)
    if match:
        raise ValidationError(f"Forbidden LaTeX command: {match.group(0)}")
    if "\\documentclass" not in source or "\\end{document}" not in source:
        raise ValidationError("Rendered LaTeX is missing document boundaries")
