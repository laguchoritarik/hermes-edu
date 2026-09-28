"""The LaTeX adapter confines output and rejects unsafe input."""

import subprocess
from pathlib import Path
from typing import cast

import pytest

from hermes_edu.documents.latex.compiler import compile_latex
from hermes_edu.documents.latex.pipeline import LatexDocumentAdapter
from hermes_edu.documents.latex.validator import validate_latex
from hermes_edu.domain.errors import CompilationError, ValidationError
from hermes_edu.domain.models.document import TDDraft
from hermes_edu.domain.models.exercise import Exercise
from hermes_edu.domain.models.source import SourceReference


def test_renderer_escapes_untrusted_tex_and_confines_thread(tmp_path: Path) -> None:
    adapter = LatexDocumentAdapter(tmp_path, engine="missing-xelatex", compile_pdf=True)
    draft = TDDraft("Test", (Exercise("One", r"\input{/etc/passwd}", "Answer", ("s1",)),))
    sources = (SourceReference("s1", "Synthetic", "local", "CC0"),)
    with pytest.raises(ValidationError):
        adapter.render(draft, sources, thread_id="../escape")
    tex = adapter.render(draft, sources, thread_id="safe")
    content = Path(tex.path).read_text()
    assert r"\textbackslash{}input" in content
    validate_latex(content)
    with pytest.raises(CompilationError, match="not installed"):
        adapter.compile(tex)


def test_validator_rejects_raw_io() -> None:
    with pytest.raises(ValidationError, match="Forbidden"):
        validate_latex(r"\documentclass{article}\begin{document}\input{secret}\end{document}")


def test_compiler_uses_fixed_flags_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "td.tex"
    source.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")
    seen: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        seen.update({"command": command, "timeout": timeout, "cwd": cwd, "env": env})
        source.with_suffix(".pdf").write_bytes(b"%PDF-1.4" + b"x" * 200)
        return subprocess.CompletedProcess(command, 0, "", "")

    def fake_which(engine: str) -> str:
        return "/usr/bin/xelatex"

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("subprocess.run", fake_run)
    result = compile_latex(source, timeout_seconds=7)
    assert result.pdf_path.is_file()
    assert "-no-shell-escape" in cast("list[str]", seen["command"])
    assert seen["timeout"] == 7
