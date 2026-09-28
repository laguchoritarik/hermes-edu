"""Typed document compilation diagnostics."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CompileResult:
    pdf_path: Path
    log_path: Path
    exit_code: int
    diagnostic: str
