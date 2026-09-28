"""Deterministic regex-based repairs for rendered LaTeX sources."""

import re
from collections.abc import Callable

from hermes_edu.documents.latex.validator import validate_latex
from hermes_edu.domain.errors import ValidationError

_FILE_LINE = re.compile(r"(?m)(?:^|\s)[^:\n]*\.tex:(\d+):")
_L_DOT_LINE = re.compile(r"(?m)^l\.(\d+)\s")
_CONTROL_WORD = re.compile(r"\\([A-Za-z]+)")
_BARE_UNDERSCORE = re.compile(r"(?<!\\)_")
_BARE_CARET = re.compile(r"(?<!\\)\^")
_UNICODE_REPLACEMENTS = {
    "\u2212": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2264": r"$\leq$",
    "\u2265": r"$\geq$",
    "\u221e": r"$\infty$",
    "\u2205": r"$\emptyset$",
    "\u2208": r"$\in$",
    "\u2227": r"$\wedge$",
    "\u222a": r"$\cup$",
    "\u2282": r"$\subset$",
    "\u2286": r"$\subseteq$",
    "\u2261": r"$\equiv$",
    "\u00d7": r"$\times$",
    "\u2218": r"$\circ$",
    "\u2295": r"$\oplus$",
    "\u2192": r"$\to$",
    "\u21a6": r"$\mapsto$",
    "\u21d2": r"$\Rightarrow$",
    "\u21d4": r"$\Leftrightarrow$",
    "\u2026": r"\ldots{}",
    "\u03bb": r"$\lambda$",
    "\u03bc": r"$\mu$",
    "\u03c6": r"$\varphi$",
    "\u2115": r"$\mathbb{N}$",
    "\u2124": r"$\mathbb{Z}$",
    "\u211d": r"$\mathbb{R}$",
    "\u2102": r"$\mathbb{C}$",
}
_SAFE_CONTROL_WORDS = frozenset(
    {
        "addvspace",
        "arabic",
        "begin",
        "bfseries",
        "bigskip",
        "caption",
        "centering",
        "cite",
        "clearpage",
        "color",
        "documentclass",
        "emph",
        "end",
        "fancyfoot",
        "fancyhead",
        "footnotesize",
        "frac",
        "hfill",
        "hspace",
        "href",
        "int",
        "item",
        "label",
        "large",
        "Large",
        "left",
        "lim",
        "mathbb",
        "mathcal",
        "mathrm",
        "newpage",
        "nobreak",
        "noindent",
        "normalsize",
        "par",
        "qquad",
        "quad",
        "ref",
        "right",
        "section",
        "small",
        "smallskip",
        "subsection",
        "subsubsection",
        "sum",
        "text",
        "textbar",
        "textbf",
        "textit",
        "textsc",
        "textsuperscript",
        "to",
        "url",
        "vspace",
    }
)


def repair_latex_source(source: str, diagnostic: str) -> str:
    """Apply bounded line-oriented fixes based on compiler diagnostics.

    This is intentionally narrow. It removes or escapes only the exact lines implicated
    by LaTeX diagnostics and refuses when no deterministic regex rule applies.
    """
    repaired = _replace_known_unicode(source)
    line_numbers = _diagnostic_line_numbers(diagnostic)
    if "Undefined control sequence" in diagnostic and line_numbers:
        repaired = _repair_lines(repaired, line_numbers, _remove_unknown_control_words)
    if "Missing $ inserted" in diagnostic and line_numbers:
        repaired = _repair_lines(repaired, line_numbers, _escape_text_subscripts)
    validate_latex(repaired)
    if repaired == source:
        raise ValidationError("No deterministic LaTeX repair matched the compiler diagnostic")
    return repaired


def _replace_known_unicode(source: str) -> str:
    repaired = source
    for character, replacement in _UNICODE_REPLACEMENTS.items():
        repaired = repaired.replace(character, replacement)
    return repaired


def _diagnostic_line_numbers(diagnostic: str) -> tuple[int, ...]:
    found = {
        int(match.group(1))
        for pattern in (_FILE_LINE, _L_DOT_LINE)
        for match in pattern.finditer(diagnostic)
    }
    return tuple(sorted(found))


def _repair_lines(source: str, line_numbers: tuple[int, ...], repair: Callable[[str], str]) -> str:
    lines = source.splitlines(keepends=True)
    for line_number in line_numbers:
        index = line_number - 1
        if 0 <= index < len(lines):
            lines[index] = repair(lines[index])
    return "".join(lines)


def _remove_unknown_control_words(line: str) -> str:
    def replace(match: re.Match[str]) -> str:
        command = match.group(1)
        return match.group(0) if command in _SAFE_CONTROL_WORDS else ""

    return _CONTROL_WORD.sub(replace, line)


def _escape_text_subscripts(line: str) -> str:
    return _BARE_CARET.sub(r"\textasciicircum{}", _BARE_UNDERSCORE.sub(r"\_", line))
