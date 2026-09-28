"""Fixed XeLaTeX process wrapper with timeout and shell escape disabled."""

import shutil
import subprocess
from pathlib import Path

from hermes_edu.documents.models import CompileResult
from hermes_edu.domain.errors import CompilationError


def compile_latex(
    source_path: Path, *, engine: str = "xelatex", timeout_seconds: int = 60
) -> CompileResult:
    """Compile a validated file inside its own workspace directory."""
    executable = shutil.which(engine)
    if executable is None:
        raise CompilationError(f"{engine} is not installed; install TeX Live or use --tex-only")
    command = [
        executable,
        "-no-shell-escape",
        "-halt-on-error",
        "-interaction=nonstopmode",
        "-file-line-error",
        f"-output-directory={source_path.parent}",
        source_path.name,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=source_path.parent,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env={"PATH": str(Path(executable).parent), "HOME": str(source_path.parent)},
        )
    except subprocess.TimeoutExpired as exc:
        raise CompilationError(f"XeLaTeX exceeded {timeout_seconds} seconds") from exc
    pdf_path = source_path.with_suffix(".pdf")
    log_path = source_path.with_suffix(".log")
    diagnostic = _compile_diagnostic(completed.stdout + "\n" + completed.stderr)
    if completed.returncode != 0:
        raise CompilationError(
            f"XeLaTeX exited {completed.returncode}: {diagnostic or completed.stderr[-1000:]}"
        )
    critical_warnings = _critical_warnings(completed.stdout + "\n" + completed.stderr)
    if critical_warnings:
        raise CompilationError(f"XeLaTeX produced critical warnings: {critical_warnings}")
    if not pdf_path.is_file() or pdf_path.stat().st_size < 100:
        raise CompilationError("XeLaTeX exited successfully but produced no usable PDF")
    return CompileResult(pdf_path, log_path, completed.returncode, diagnostic)


def _compile_diagnostic(output: str) -> str:
    lines = output.splitlines()
    selected: list[str] = []
    for index, line in enumerate(lines):
        if "!" not in line and not line.startswith("l."):
            continue
        selected.extend(lines[max(0, index - 1) : min(len(lines), index + 3)])
    return "\n".join(dict.fromkeys(selected))[:4000]


def _critical_warnings(output: str) -> str:
    selected = [
        line
        for line in output.splitlines()
        if any(
            marker in line
            for marker in (
                "LaTeX Warning: Reference",
                "Missing character:",
                "Undefined control sequence",
                "Package inputenc Error",
            )
        )
    ]
    return "\n".join(dict.fromkeys(selected))[:4000]
