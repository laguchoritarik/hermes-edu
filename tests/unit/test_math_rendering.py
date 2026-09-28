"""Regression tests for preserving mathematical LaTeX spans during rendering."""

import pytest

from hermes_edu.documents.latex.math_content import render_math_text, validate_math_text


@pytest.mark.parametrize(
    "formula",
    (
        r"$M_n(K)$",
        r"$C^k(I,K)$",
        r"$1_E$",
        r"$\operatorname{Mat}_{\mathcal B}(f)$",
        r"$f\circ g$",
        r"$\lambda\cdot x$",
        r"$a^{\varphi(n)}$",
        r"$\overline{a}+\overline{b}=\overline{a+b}$",
    ),
)
def test_math_spans_are_preserved_without_text_escape(formula: str) -> None:
    validate_math_text(formula)
    rendered = render_math_text(f"On utilise {formula}.")

    assert formula in rendered
    assert r"\_" not in rendered
    assert r"\textasciicircum{}" not in rendered
