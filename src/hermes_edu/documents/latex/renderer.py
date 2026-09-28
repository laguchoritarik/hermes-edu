"""Safe Jinja2 rendering of plain-text TD content."""

from importlib.resources import files

from jinja2 import Environment, StrictUndefined

from hermes_edu.domain.models.document import TDDraft
from hermes_edu.domain.models.source import SourceReference

_ESCAPE = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "%": r"\%",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "_": r"\_",
    "^": r"\textasciicircum{}",
    "~": r"\textasciitilde{}",
}


def escape_latex(text: str) -> str:
    """Treat all model-authored content as text, including apparent TeX commands."""
    return "".join(_ESCAPE.get(character, character) for character in text)


def render_td(draft: TDDraft, sources: tuple[SourceReference, ...]) -> str:
    template_text = files("hermes_edu.documents.templates").joinpath("td_v1.tex.j2").read_text()
    environment = Environment(autoescape=False, undefined=StrictUndefined)
    environment.filters["tex"] = escape_latex
    template = environment.from_string(template_text)
    return template.render(draft=draft, sources=sources)
