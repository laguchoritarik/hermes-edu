"""Page-aware extraction of mathematical blocks from text PDFs or OCR output."""

# PyMuPDF's dynamic page API has incomplete static stubs.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

import re
from hashlib import sha256
from typing import Protocol, cast

import pymupdf

from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.reference import MathBlock, ParsedReference

_HEADING = re.compile(
    r"^(chapitre|chapter|section|sous-section|subsection)\s+([\d.IVXivx]+)?\s*[:. -]*\s*(.*)$", re.I
)
_BLOCK = re.compile(
    r"^(définition|definition|théorème|theorem|proposition|lemme|lemma|corollaire|corollary|"
    r"propriété|property|résultat|result|démonstration|preuve|proof|remark|remarque|"
    r"exemple|example|contre-exemple|counterexample|méthode|method|application|"
    r"exercice|exercise|question|solution|correction|équation|equation|tableau|table|"
    r"figure)\s*([\d.]+)?\s*[:. -]*\s*(.*)$",
    re.I,
)
_TYPES = {
    "définition": "definition",
    "definition": "definition",
    "théorème": "theorem",
    "theorem": "theorem",
    "proposition": "proposition",
    "lemme": "lemma",
    "lemma": "lemma",
    "corollaire": "corollary",
    "corollary": "corollary",
    "propriété": "property",
    "property": "property",
    "résultat": "result",
    "result": "result",
    "démonstration": "proof",
    "preuve": "proof",
    "proof": "proof",
    "remark": "remark",
    "remarque": "remark",
    "exemple": "example",
    "example": "example",
    "contre-exemple": "counterexample",
    "counterexample": "counterexample",
    "méthode": "method",
    "method": "method",
    "application": "application",
    "exercice": "exercise",
    "exercise": "exercise",
    "question": "question",
    "solution": "solution",
    "correction": "solution",
    "équation": "equation",
    "equation": "equation",
    "tableau": "table",
    "table": "table",
    "figure": "figure",
}
_LATEX_HEADING = re.compile(r"^\\(chapter|section|subsection)\*?\{([^}]*)\}")
_LATEX_BEGIN = re.compile(r"^\\begin\{([A-Za-z*]+)\}(?:\[([^]]*)\])?(.*)$")
_LATEX_END = re.compile(r"^\\end\{[A-Za-z*]+\}$")
_LATEX_BLOCKS = {
    "definition": "Définition",
    "theorem": "Théorème",
    "proposition": "Proposition",
    "lemma": "Lemme",
    "corollary": "Corollaire",
    "proof": "Preuve",
    "remark": "Remarque",
    "example": "Exemple",
    "exercise": "Exercice",
    "solution": "Solution",
    "equation": "Équation",
    "align": "Équation",
}


def _structured_line(raw_line: str) -> str:
    """Expose LaTeX headings and environments while keeping formula bodies unchanged."""
    line = raw_line.strip()
    heading = _LATEX_HEADING.match(line)
    if heading:
        return f"{heading.group(1)} {heading.group(2)}"
    begin = _LATEX_BEGIN.match(line)
    if begin:
        if begin.group(1) == "document":
            return ""
        kind = _LATEX_BLOCKS.get(begin.group(1).rstrip("*"))
        if kind:
            return " ".join(part for part in (kind, begin.group(2), begin.group(3)) if part)
    if _LATEX_END.match(line) or line.startswith(("\\documentclass", "\\usepackage")):
        return ""
    return line


class OCRPort(Protocol):
    @property
    def version(self) -> str: ...
    def convert(self, pdf_bytes: bytes) -> str: ...


class StructuredPDFParser:
    """Structure converted LaTeX, with explicit local text mode for offline use."""

    version = "pymupdf-math-blocks-v1"

    def __init__(
        self,
        ocr: OCRPort | None = None,
        *,
        min_text_characters: int = 40,
        require_conversion: bool = False,
    ) -> None:
        self._ocr = ocr
        self._min_text = min_text_characters
        self._require_conversion = require_conversion
        if require_conversion:
            self.version = f"{self.version}:latex-v1"

    @property
    def ocr_version(self) -> str:
        return self._ocr.version if self._ocr else "none"

    def parse(self, content: bytes, document_id: str) -> ParsedReference:
        try:
            with pymupdf.open(stream=content, filetype="pdf") as pdf:
                page_count = cast(int, pdf.page_count)
                if page_count > 200 or cast(bool, pdf.needs_pass):
                    raise ValidationError("PDF must be unencrypted and at most 200 pages")
                pages = (
                    []
                    if self._require_conversion
                    else [cast(str, page.get_text("text", sort=True)) for page in pdf]
                )
        except (RuntimeError, ValueError) as exc:
            raise ValidationError("PDF parsing failed") from exc
        ocr_used = self._require_conversion or (
            sum(len(page.strip()) for page in pages) < self._min_text * page_count
        )
        source_latex = ""
        if ocr_used:
            if self._ocr is None:
                raise ValidationError("PDF to LaTeX conversion requires ILOVEMYLATEX_API_KEY")
            source_latex = self._ocr.convert(content)
            pages = [source_latex]
        blocks = self._blocks(pages, document_id, page_count if ocr_used else 1)
        if not blocks:
            raise ValidationError("PDF contains no usable mathematical text")
        return ParsedReference(document_id, blocks, ocr_used, source_latex)

    @staticmethod
    def _blocks(pages: list[str], document_id: str, ocr_page_end: int) -> tuple[MathBlock, ...]:
        blocks: list[MathBlock] = []
        chapter = section = subsection = ""
        current: list[str] = []
        block_type = "paragraph"
        number = title = relation = related = ""
        start_page = end_page = 1
        last_claim = last_exercise = ""

        def flush() -> None:
            nonlocal current, last_claim, last_exercise
            text = "\n".join(current).strip()
            if not text:
                current = []
                return
            block_id = sha256(f"{document_id}:{len(blocks)}:{text}".encode()).hexdigest()[:32]
            blocks.append(
                MathBlock(
                    block_id,
                    block_type,
                    text,
                    start_page,
                    end_page,
                    chapter,
                    section,
                    subsection,
                    number,
                    title,
                    relation,
                    related,
                )
            )
            if block_type in {"theorem", "proposition", "lemma", "corollary"}:
                last_claim = block_id
            elif block_type == "exercise":
                last_exercise = block_id
            current = []

        for page_number, page_text in enumerate(pages, start=1):
            for raw_line in page_text.splitlines():
                line = _structured_line(raw_line)
                if not line:
                    if current:
                        current.append("")
                    continue
                heading = _HEADING.match(line)
                object_match = _BLOCK.match(line)
                if heading:
                    flush()
                    label = heading.group(1).lower()
                    name = " ".join(part for part in heading.groups()[1:] if part)
                    if label in {"chapitre", "chapter"}:
                        chapter, section, subsection = name, "", ""
                    elif label == "section":
                        section, subsection = name, ""
                    else:
                        subsection = name
                    continue
                if object_match:
                    flush()
                    block_type = _TYPES[object_match.group(1).lower()]
                    number = object_match.group(2) or ""
                    title = object_match.group(3) or ""
                    relation = (
                        "proof_of"
                        if block_type == "proof" and last_claim
                        else "example_of"
                        if block_type in {"example", "counterexample"} and last_claim
                        else "solution_of"
                        if block_type == "solution" and last_exercise
                        else ""
                    )
                    related = (
                        last_claim
                        if relation in {"proof_of", "example_of"}
                        else last_exercise
                        if relation == "solution_of"
                        else ""
                    )
                    start_page = page_number
                elif not current:
                    block_type, number, title, relation, related = "paragraph", "", "", "", ""
                    start_page = page_number
                end_page = ocr_page_end if len(pages) == 1 and ocr_page_end > 1 else page_number
                current.append(line)
        flush()
        return tuple(blocks)
