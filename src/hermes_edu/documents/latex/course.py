"""Workspace-confined LaTeX course artifact production."""

import hashlib
import json
import re
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, StrictUndefined

from hermes_edu.config.paths import confined_path
from hermes_edu.documents.latex.compiler import compile_latex
from hermes_edu.documents.latex.math_content import render_math_text, validate_math_text
from hermes_edu.documents.latex.renderer import escape_latex
from hermes_edu.documents.latex.repair import repair_latex_source
from hermes_edu.documents.latex.validator import validate_latex
from hermes_edu.documents.pdf.inspector import inspect_pdf
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.course import CourseDraft
from hermes_edu.domain.models.document import Artifact
from hermes_edu.domain.models.quality import QualityReport
from hermes_edu.domain.models.source import SourceReference

_THREAD_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")
_BLOCK_ENVIRONMENTS = frozenset(
    {
        "theorem",
        "proposition",
        "lemma",
        "corollary",
        "result",
        "proof",
        "example",
        "method",
        "remark",
        "definition",
        "text",
        "exercise",
        "solution",
    }
)
_BLOCK_KINDS = _BLOCK_ENVIRONMENTS | {"heading"}


class LatexCourseAdapter:
    """Render a structured course with a fixed template and restricted math grammar."""

    def __init__(
        self,
        workspace: Path,
        *,
        engine: str = "xelatex",
        timeout_seconds: int = 60,
        compile_pdf: bool = True,
        template_path: Path | None = None,
    ) -> None:
        self._workspace = workspace.resolve()
        self._engine = engine
        self._timeout_seconds = timeout_seconds
        self._compile_pdf = compile_pdf
        self._template_path = template_path.resolve() if template_path else None

    def render(
        self,
        draft: CourseDraft,
        sources: tuple[SourceReference, ...],
        *,
        thread_id: str,
    ) -> Artifact:
        if not _THREAD_ID.fullmatch(thread_id):
            raise ValidationError(
                "Thread ID must contain 1-80 letters, digits, hyphens or underscores"
            )
        directory = confined_path(self._workspace, self._workspace / thread_id)
        directory.mkdir(parents=True, exist_ok=True)
        tex_path = confined_path(self._workspace, directory / "course.tex")
        tex_path.write_text(
            _render_course(draft, sources, template_path=self._template_path),
            encoding="utf-8",
        )
        validate_latex(tex_path.read_text(encoding="utf-8"))
        return _artifact(tex_path, "tex")

    def compile(self, tex_artifact: Artifact) -> Artifact | None:
        if not self._compile_pdf:
            return None
        tex_path = confined_path(self._workspace, Path(tex_artifact.path))
        if tex_path.name != "course.tex" or not tex_path.is_file():
            raise ValidationError("Compilation requires a workspace course.tex artifact")
        if _artifact(tex_path, "tex").sha256 != tex_artifact.sha256:
            raise ValidationError("LaTeX source changed after rendering")
        validate_latex(tex_path.read_text(encoding="utf-8"))
        compile_latex(tex_path, engine=self._engine, timeout_seconds=self._timeout_seconds)
        result = compile_latex(tex_path, engine=self._engine, timeout_seconds=self._timeout_seconds)
        inspect_pdf(result.pdf_path)
        return _artifact(result.pdf_path, "pdf")

    def repair_latex(self, tex_artifact: Artifact, diagnostic: str) -> Artifact:
        tex_path = confined_path(self._workspace, Path(tex_artifact.path))
        if tex_path.name != "course.tex" or not tex_path.is_file():
            raise ValidationError("LaTeX repair requires a workspace course.tex artifact")
        if _artifact(tex_path, "tex").sha256 != tex_artifact.sha256:
            raise ValidationError("LaTeX source changed before repair")
        repaired = repair_latex_source(tex_path.read_text(encoding="utf-8"), diagnostic)
        tex_path.write_text(repaired, encoding="utf-8")
        return _artifact(tex_path, "tex")

    def write_quality_report(
        self, report: QualityReport, *, thread_id: str
    ) -> tuple[Artifact, ...]:
        if not _THREAD_ID.fullmatch(thread_id):
            raise ValidationError(
                "Thread ID must contain 1-80 letters, digits, hyphens or underscores"
            )
        directory = confined_path(self._workspace, self._workspace / thread_id)
        directory.mkdir(parents=True, exist_ok=True)
        json_path = confined_path(self._workspace, directory / "quality_report.json")
        md_path = confined_path(self._workspace, directory / "quality_report.md")
        json_path.write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(_quality_markdown(report), encoding="utf-8")
        return (_artifact(json_path, "quality_json"), _artifact(md_path, "quality_md"))


def _render_course(
    draft: CourseDraft,
    sources: tuple[SourceReference, ...],
    *,
    template_path: Path | None = None,
) -> str:
    if len({source.source_id for source in sources}) != len(sources):
        raise ValidationError("Supplied provenance must not repeat a source ID")
    source_keys = {
        source.source_id: f"source-{index}" for index, source in enumerate(sources, start=1)
    }
    sections: list[dict[str, object]] = []
    for section in draft.sections:
        unknown_section_sources = set(section.source_ids) - source_keys.keys()
        if unknown_section_sources:
            raise ValidationError("Course section cites a source absent from supplied provenance")
        blocks: list[dict[str, object]] = []
        cited_by_blocks: set[str] = set()
        for block in section.blocks:
            if block.kind not in _BLOCK_KINDS:
                raise ValidationError(f"Unsupported course block kind: {block.kind}")
            # ``getattr`` keeps old checkpoint drafts renderable while new drafts
            # carry source IDs for every generated block.
            block_source_ids = tuple(getattr(block, "source_ids", ()))
            unknown_block_sources = set(block_source_ids) - source_keys.keys()
            if unknown_block_sources:
                raise ValidationError("Course block cites a source absent from supplied provenance")
            if not set(block_source_ids).issubset(section.source_ids):
                raise ValidationError("Course block sources must be a subset of section sources")
            text = block.text
            for index, source in enumerate(sources, start=1):
                text = text.replace(f"[{source.source_id}]", f"[{index}]")
            validate_math_text(text)
            blocks.append(
                {
                    "kind": block.kind,
                    "content": render_math_text(text),
                    "citation_keys": tuple(
                        source_keys[source_id] for source_id in block_source_ids
                    ),
                }
            )
            cited_by_blocks.update(block_source_ids)
        sections.append(
            {
                "title": escape_latex(section.title),
                "blocks": blocks,
                "citation_keys": tuple(
                    source_keys[source_id]
                    for source_id in section.source_ids
                    if source_id not in cited_by_blocks
                ),
            }
        )
    template_text = _course_template_text(template_path)
    environment = Environment(
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        comment_start_string="/*#",
        comment_end_string="#*/",
    )
    return environment.from_string(template_text).render(
        title=escape_latex(draft.title),
        sections=sections,
        sources=tuple(
            {
                "key": source_keys[source.source_id],
                "source_id": escape_latex(source.source_id),
                "title": escape_latex(source.title),
                "location": escape_latex(source.location),
                "url": quote(source.location, safe=":/?=&%#_.-~")
                if source.location.startswith(("https://", "http://"))
                else "",
                "license": escape_latex(source.license),
            }
            for source in sources
        ),
    )


def _course_template_text(template_path: Path | None) -> str:
    if template_path is None:
        return files("hermes_edu.documents.templates").joinpath("course_v1.tex.j2").read_text()
    if not template_path.is_file():
        raise ValidationError(f"Course template not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


def _artifact(path: Path, kind: str) -> Artifact:
    content = path.read_bytes()
    return Artifact(kind, str(path), hashlib.sha256(content).hexdigest(), len(content))


def _quality_markdown(report: QualityReport) -> str:
    lines = ["# Quality report", "", f"Status: {report.status}", ""]
    if report.blockers:
        lines.append("## Blockers")
        for issue in report.blockers:
            lines.append(
                f"- [{issue.category}] section {issue.section_index}, block {issue.block_index}: {issue.message}"
            )
        lines.append("")
    if report.warnings:
        lines.append("## Warnings")
        for issue in report.warnings:
            lines.append(
                f"- [{issue.category}] section {issue.section_index}, block {issue.block_index}: {issue.message}"
            )
        lines.append("")
    lines.append("## Coverage")
    for section in report.coverage:
        lines.append(
            f"- {section.section_id} {section.title}: {section.evidence_status} ({section.evidence_score:.2f})"
        )
    lines.append("")
    return "\n".join(lines)
