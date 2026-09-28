"""Course rendering is confined and accepts only the math-content contract."""

import shutil
from pathlib import Path

import pytest

from hermes_edu.documents.latex.course import LatexCourseAdapter
from hermes_edu.documents.latex.math_content import validate_math_text
from hermes_edu.documents.latex.repair import repair_latex_source
from hermes_edu.documents.models import CompileResult
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.course import CourseBlock, CourseDraft, CourseSection
from hermes_edu.domain.models.source import SourceReference


def _draft(
    text: str = "Pour $a \\geq 0$, on pose $I(a)=\\int_0^1 \\frac{dx}{1+a x^2}$.",
) -> CourseDraft:
    return CourseDraft(
        "Intégrales dépendant d'un paramètre",
        (CourseSection("Introduction", (CourseBlock("text", text),), ("reference-1",)),),
    )


def _sources() -> tuple[SourceReference, ...]:
    return (SourceReference("reference-1", "Notes MP", "p. 4", "CC BY-SA 4.0"),)


def test_course_renderer_preserves_restricted_math_and_escapes_prose(tmp_path: Path) -> None:
    adapter = LatexCourseAdapter(tmp_path, compile_pdf=False)
    artifact = adapter.render(
        _draft("Le symbole \\input est du texte ; $\\lim_{a \\to 0} I(a)=1$."),
        _sources(),
        thread_id="course_42",
    )

    assert Path(artifact.path) == tmp_path / "course_42" / "course.tex"
    rendered = Path(artifact.path).read_text(encoding="utf-8")
    assert r"\textbackslash{}input" in rendered
    assert r"\lim_{a \to 0} I(a)=1" in rendered
    assert r"\cite" not in rendered
    assert r"\bibitem" not in rendered
    assert r"\begin{thebibliography}" not in rendered


@pytest.mark.parametrize(
    "content",
    (
        "$\\input{secret}$",
        "$x^{2$",
        "$x$$",
        "$x^^41$",
        "$\\begin{proof}x\\end{proof}$",
    ),
)
def test_math_content_rejects_control_sequences_and_invalid_structure(content: str) -> None:
    with pytest.raises(ValidationError):
        validate_math_text(content)


def test_course_renderer_rejects_path_escape_and_unknown_citation(tmp_path: Path) -> None:
    adapter = LatexCourseAdapter(tmp_path, compile_pdf=False)
    with pytest.raises(ValidationError, match="Thread ID"):
        adapter.render(_draft(), _sources(), thread_id="../outside")

    draft = CourseDraft(
        "Cours",
        (CourseSection("Section", (CourseBlock("text", "Texte."),), ("missing",)),),
    )
    with pytest.raises(ValidationError, match="absent"):
        adapter.render(draft, _sources(), thread_id="safe")


def test_course_renderer_keeps_internal_provenance_without_visible_citations(
    tmp_path: Path,
) -> None:
    adapter = LatexCourseAdapter(tmp_path, compile_pdf=False)
    attributed_block = CourseBlock("text", "Fait sourcé.", ("reference-1",))
    attributed = CourseDraft(
        "Cours",
        (CourseSection("Section", (attributed_block,), ("reference-1",)),),
    )

    artifact = adapter.render(attributed, _sources(), thread_id="attributed")
    rendered = Path(artifact.path).read_text(encoding="utf-8")
    assert "Fait sourcé." in rendered
    assert r"\cite" not in rendered
    assert r"source-1" not in rendered

    unknown_block = CourseBlock("text", "Fait inventé.", ("unknown",))
    invalid = CourseDraft(
        "Cours",
        (CourseSection("Section", (unknown_block,), ("reference-1",)),),
    )
    with pytest.raises(ValidationError, match="Course block cites"):
        adapter.render(invalid, _sources(), thread_id="invalid")


def test_course_renderer_accepts_external_jinja_template(tmp_path: Path) -> None:
    template = tmp_path / "course-template.tex"
    template.write_text(
        r"""\documentclass{article}
\begin{document}
\section*{ {{ title }} }
{% for section in sections %}
\subsection*{ {{ section.title }} }
{% for block in section.blocks %}
{{ block.content }}
{% endfor %}
{% endfor %}
\end{document}
""",
        encoding="utf-8",
    )
    adapter = LatexCourseAdapter(tmp_path, compile_pdf=False, template_path=template)

    artifact = adapter.render(_draft("Texte externe $x\\leqslant y$."), _sources(), thread_id="ext")

    rendered = Path(artifact.path).read_text(encoding="utf-8")
    assert r"\section*{ Intégrales dépendant d'un paramètre }" in rendered
    assert r"Texte externe $x\leqslant y$." in rendered


def test_course_compilation_runs_twice_for_the_table_of_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = LatexCourseAdapter(tmp_path)
    tex = adapter.render(_draft(), _sources(), thread_id="toc")
    calls = 0

    def fake_compile(source: Path, *, engine: str, timeout_seconds: int) -> CompileResult:
        nonlocal calls
        calls += 1
        pdf = source.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF-1.4" + b"x" * 200)
        return CompileResult(pdf, source.with_suffix(".log"), 0, "")

    def fake_inspect(_: Path) -> None:
        return None

    monkeypatch.setattr("hermes_edu.documents.latex.course.compile_latex", fake_compile)
    monkeypatch.setattr("hermes_edu.documents.latex.course.inspect_pdf", fake_inspect)

    pdf = adapter.compile(tex)

    assert calls == 2
    assert pdf is not None
    assert Path(pdf.path) == tmp_path / "toc" / "course.pdf"


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is not installed")
def test_course_template_compiles_a_paragraph_with_pdflatex(tmp_path: Path) -> None:
    adapter = LatexCourseAdapter(tmp_path, engine="pdflatex")
    tex = adapter.render(
        _draft(
            "Premier paragraphe.\n\nSecond paragraphe avec $\\ell(a) \\to 0$, "
            "$\\|f\\|_\\infty$ et $\\left\\|f\\right\\|$."
        ),
        _sources(),
        thread_id="pdflatex",
    )

    rendered = Path(tex.path).read_text(encoding="utf-8")
    assert r"\|f\|_\infty" in rendered
    assert r"\left\|f\right\|" in rendered

    pdf = adapter.compile(tex)

    assert pdf is not None
    assert Path(pdf.path).name == "course.pdf"


def test_course_accepts_common_analysis_notation_and_rejects_incomplete_command() -> None:
    validate_math_text(
        r"$\lfloor x\rfloor \leq x < \lceil x\rceil$, $\|f\|_\infty$ et "
        r"$\boxed{\lim_{n\to\infty} u_n=\ell}$, $d \mid k$, $a \wedge b$, "
        r"$E \oplus F$, $\binom{n}{k}$, $\dim(E)$ et $\therefore x=0$"
    )
    with pytest.raises(ValidationError, match="incomplete command"):
        validate_math_text("$x\\$")


def test_latex_repair_removes_unknown_control_sequence_on_reported_line() -> None:
    source = "\n".join(
        (
            r"\documentclass{article}",
            r"\begin{document}",
            r"Texte \badmacro{} avec contenu.",
            r"\end{document}",
        )
    )

    repaired = repair_latex_source(
        source,
        "XeLaTeX exited 1: ./course.tex:3: Undefined control sequence.\nl.3 Texte \\badmacro{}",
    )

    assert r"\badmacro" not in repaired
    assert "avec contenu" in repaired


def test_latex_repair_replaces_common_unicode_math_symbols() -> None:
    source = "\n".join(
        (
            r"\documentclass{article}",
            r"\begin{document}",
            "Un idéal I vérifie I = nZ avec n \u2208 \u2115 et k \u2227 n = 1; "
            "\u03c6(n)=|U(Z/nZ)|.",
            r"\end{document}",
        )
    )

    repaired = repair_latex_source(
        source,
        "XeLaTeX exited 1: ./course.tex:3: Missing $ inserted.\nl.3 n \u2208 \u2115",
    )

    assert r"$\in$" in repaired
    assert r"$\mathbb{N}$" in repaired
    assert r"$\wedge$" in repaired
    assert r"$\varphi$" in repaired
