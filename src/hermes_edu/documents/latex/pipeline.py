"""Workspace-confined TD artifact production."""

import hashlib
import re
from pathlib import Path

from hermes_edu.application.ports.compiler import DocumentPort
from hermes_edu.config.paths import confined_path
from hermes_edu.documents.latex.compiler import compile_latex
from hermes_edu.documents.latex.renderer import render_td
from hermes_edu.documents.latex.validator import validate_latex
from hermes_edu.documents.pdf.inspector import inspect_pdf
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.document import Artifact, TDDraft
from hermes_edu.domain.models.source import SourceReference


def _artifact(path: Path, kind: str) -> Artifact:
    content = path.read_bytes()
    return Artifact(kind, str(path), hashlib.sha256(content).hexdigest(), len(content))


class LatexDocumentAdapter(DocumentPort):
    def __init__(
        self,
        workspace: Path,
        *,
        engine: str = "xelatex",
        timeout_seconds: int = 60,
        compile_pdf: bool = True,
    ) -> None:
        self._workspace = workspace.resolve()
        self._engine = engine
        self._timeout_seconds = timeout_seconds
        self._compile_pdf = compile_pdf

    def render(
        self, draft: TDDraft, sources: tuple[SourceReference, ...], *, thread_id: str
    ) -> Artifact:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", thread_id):
            raise ValidationError(
                "Thread ID must contain 1-80 letters, digits, hyphens or underscores"
            )
        directory = confined_path(self._workspace, self._workspace / thread_id)
        directory.mkdir(parents=True, exist_ok=True)
        source = render_td(draft, sources)
        validate_latex(source)
        tex_path = confined_path(self._workspace, directory / "td.tex")
        tex_path.write_text(source, encoding="utf-8")
        return _artifact(tex_path, "tex")

    def compile(self, tex_artifact: Artifact) -> Artifact | None:
        if not self._compile_pdf:
            return None
        tex_path = confined_path(self._workspace, Path(tex_artifact.path))
        if tex_path.suffix != ".tex" or not tex_path.is_file():
            raise ValidationError("Compilation requires a workspace .tex artifact")
        if _artifact(tex_path, "tex").sha256 != tex_artifact.sha256:
            raise ValidationError("LaTeX source changed after rendering")
        validate_latex(tex_path.read_text(encoding="utf-8"))
        result = compile_latex(tex_path, engine=self._engine, timeout_seconds=self._timeout_seconds)
        inspect_pdf(result.pdf_path)
        return _artifact(result.pdf_path, "pdf")


def artifact_for_path(path: Path, kind: str) -> Artifact:
    """Describe an existing file for a controlled adapter operation."""
    return _artifact(path, kind)
