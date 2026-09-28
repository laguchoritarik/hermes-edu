"""Validation and safe rendering for the deliberately small math-content grammar."""

import re

from hermes_edu.documents.latex.renderer import escape_latex
from hermes_edu.domain.errors import ValidationError

_COMMAND = re.compile(r"\\([A-Za-z]+|.)")
_ALLOWED_COMMANDS = frozenset(
    {
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "varepsilon",
        "zeta",
        "eta",
        "theta",
        "vartheta",
        "iota",
        "kappa",
        "lambda",
        "mu",
        "nu",
        "xi",
        "pi",
        "rho",
        "sigma",
        "tau",
        "upsilon",
        "phi",
        "varphi",
        "chi",
        "psi",
        "omega",
        "Gamma",
        "Delta",
        "Theta",
        "Lambda",
        "Xi",
        "Pi",
        "Sigma",
        "Upsilon",
        "Phi",
        "Psi",
        "Omega",
        "lfloor",
        "rfloor",
        "lceil",
        "rceil",
        "langle",
        "rangle",
        "big",
        "Big",
        "bigg",
        "Bigg",
        "biggl",
        "biggr",
        "Biggl",
        "Biggr",
        "limits",
        "equiv",
        "iff",
        "implies",
        "ne",
        "not",
        "Re",
        "Im",
        "emptyset",
        "setminus",
        "backslash",
        "boxed",
        "stackrel",
        "binom",
        "hat",
        "widehat",
        "tilde",
        "widetilde",
        "bar",
        "vec",
        "frac",
        "dfrac",
        "tfrac",
        "sqrt",
        "left",
        "right",
        "bigl",
        "bigr",
        "Bigl",
        "Bigr",
        "lvert",
        "rvert",
        "lVert",
        "rVert",
        "cdot",
        "times",
        "div",
        "pm",
        "mp",
        "mid",
        "le",
        "leq",
        "leqslant",
        "ge",
        "geq",
        "geqslant",
        "neq",
        "approx",
        "sim",
        "therefore",
        "infty",
        "ldots",
        "dots",
        "cdots",
        "partial",
        "nabla",
        "lim",
        "sum",
        "prod",
        "int",
        "iint",
        "iiint",
        "forall",
        "exists",
        "in",
        "notin",
        "subset",
        "subseteq",
        "supset",
        "supseteq",
        "cup",
        "cap",
        "wedge",
        "mathbb",
        "mathcal",
        "operatorname",
        "underbrace",
        "overbrace",
        "quad",
        "qquad",
        "colon",
        "vert",
        "Vert",
        "to",
        "mapsto",
        "longrightarrow",
        "longleftrightarrow",
        "Rightarrow",
        "Leftrightarrow",
        "circ",
        "circledast",
        "oplus",
        "prime",
        "log",
        "ln",
        "exp",
        "sin",
        "cos",
        "tan",
        "arcsin",
        "arccos",
        "arctan",
        "max",
        "min",
        "sup",
        "inf",
        "det",
        "dim",
        "ker",
        "mathrm",
        "mathbf",
        "mathit",
        "text",
        "ell",
        "xrightarrow",
        "overline",
        "overrightarrow",
        "",
        "{",
        "}",
        "_",
        "^",
        "%",
        "&",
        "#",
        "|",
        " ",
        ",",
        ";",
        ":",
        "!",
    }
)
_DISALLOWED_MATH_CHARACTERS = frozenset({"%", "#", "&", "~", "`"})


def validate_math_text(text: str) -> None:
    """Validate prose containing only plain text plus ``$...$`` or ``$$...$$`` math.

    The accepted TeX subset is intentionally insufficient for document control, file I/O,
    environments, or user-defined macros.  It exists solely for mathematical notation.
    """
    if "^^" in text:
        raise ValidationError("Math content must not contain TeX character-code escapes (^^)")

    position = 0
    text_length = len(text)
    while position < text_length:
        delimiter_at = text.find("$", position)
        if delimiter_at == -1:
            return
        display = text.startswith("$$", delimiter_at)
        delimiter = "$$" if display else "$"
        content_start = delimiter_at + len(delimiter)
        content_end = text.find(delimiter, content_start)
        if content_end == -1:
            raise ValidationError("Math delimiters are not balanced")
        math = text[content_start:content_end]
        if "$" in math:
            raise ValidationError("Math delimiters cannot be nested or mixed")
        if not math.strip():
            raise ValidationError("Math delimiters must contain an expression")
        _validate_math_expression(math)
        position = content_end + len(delimiter)


def render_math_text(text: str) -> str:
    """Escape prose while preserving validated inline and display mathematical notation."""
    validate_math_text(text)
    rendered: list[str] = []
    position = 0
    while position < len(text):
        delimiter_at = text.find("$", position)
        if delimiter_at == -1:
            rendered.append(_render_prose(text[position:]))
            break
        rendered.append(_render_prose(text[position:delimiter_at]))
        delimiter = "$$" if text.startswith("$$", delimiter_at) else "$"
        content_start = delimiter_at + len(delimiter)
        content_end = text.find(delimiter, content_start)
        rendered.append(delimiter)
        rendered.append(text[content_start:content_end])
        rendered.append(delimiter)
        position = content_end + len(delimiter)
    return "".join(rendered)


def _render_prose(prose: str) -> str:
    return escape_latex(prose).replace("\n\n", "\\par\n").replace("\n", " ")


def _validate_math_expression(expression: str) -> None:
    if any(character in _DISALLOWED_MATH_CHARACTERS for character in expression):
        raise ValidationError("Math expressions contain a reserved TeX character")
    expression_without_literal_braces = _COMMAND.sub(
        lambda match: "" if match.group(1) in {"{", "}"} else match.group(0), expression
    )
    depth = 0
    for character in expression_without_literal_braces:
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise ValidationError("Math expression has unmatched closing braces")
    if depth:
        raise ValidationError("Math expression has unmatched braces")
    if expression.endswith("\\"):
        raise ValidationError("Math expression ends with an incomplete command")
    for match in _COMMAND.finditer(expression):
        command = match.group(1)
        if command not in _ALLOWED_COMMANDS:
            raise ValidationError(f"Math command is not allowed: \\{command}")
