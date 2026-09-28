"""Regression tests for deterministic document quality gates."""

from hermes_edu.application.services.document_quality import DocumentQualityGate
from hermes_edu.domain.enums import Severity
from hermes_edu.domain.models.course import (
    CourseBlock,
    CourseDraft,
    CoursePlan,
    CourseSection,
    PlannedSection,
)
from hermes_edu.domain.models.quality import QualityStatus
from hermes_edu.domain.models.source import RetrievedChunk, SourceReference


def _plan() -> CoursePlan:
    return CoursePlan("Algèbre", (PlannedSection("Anneaux", "Idéaux", ("official",)),))


def _chunk(identifier: str = "ref:1") -> RetrievedChunk:
    return RetrievedChunk(
        identifier,
        "Passage sourcé.",
        SourceReference(identifier, "Cours", "p. 1", "local"),
        1.0,
    )


def _report(blocks: tuple[CourseBlock, ...], chunks: tuple[RetrievedChunk, ...] = (_chunk(),)):
    draft = CourseDraft("Algèbre", (CourseSection("Anneaux", blocks, ("ref:1",)),))
    return DocumentQualityGate().evaluate_course(
        plan=_plan(),
        draft=draft,
        section_chunks=(chunks,),
        sources=tuple(chunk.source for chunk in chunks),
    )


def test_obvious_subgroup_intersection_error_is_blocker() -> None:
    report = _report(
        (
            CourseBlock(
                "text", "Les sous-groupes $2Z$ et $3Z$ ne se rencontrent qu'en $0$.", ("ref:1",)
            ),
        )
    )

    assert report.status == QualityStatus.DRAFT
    assert any(
        issue.category == "math" and issue.severity is Severity.BLOCKER for issue in report.blockers
    )


def test_statement_solution_field_switch_is_detected() -> None:
    report = _report(
        (
            CourseBlock("exercise", "Soit $A\\in M_n(K)$.", ("ref:1",)),
            CourseBlock("solution", "On considère alors $A\\in M_n(R)$.", ("ref:1",)),
        )
    )

    assert any(issue.category == "notation" for issue in report.blockers)


def test_duplicate_definitions_are_blocked() -> None:
    text = "Une K-algèbre est un K-espace vectoriel muni d'une multiplication bilinéaire."
    report = _report(
        (
            CourseBlock("definition", text, ("ref:1",)),
            CourseBlock("definition", text, ("ref:1",)),
        )
    )

    assert any(issue.category == "duplicates" for issue in report.blockers)


def test_mandatory_section_without_sources_requests_reference() -> None:
    report = _report((CourseBlock("text", "Contenu.", ("ref:1",)),), chunks=())

    assert report.status == QualityStatus.DRAFT
    assert report.source_gaps


def test_internal_rag_comment_is_not_allowed_in_student_content() -> None:
    report = _report(
        (
            CourseBlock(
                "text",
                "Les références dont nous disposons ne fournissent pas cette preuve.",
                ("ref:1",),
            ),
        )
    )

    assert any(issue.category == "content_policy" for issue in report.blockers)


def test_source_metadata_contamination_is_blocked() -> None:
    source = SourceReference("ref:1", "Tarik Laguchori - Lycée - Tanger", "p. 1", "local")
    draft = CourseDraft(
        "Algèbre",
        (
            CourseSection(
                "Anneaux",
                (CourseBlock("text", "Cours de Tarik Laguchori.", ("ref:1",)),),
                ("ref:1",),
            ),
        ),
    )
    report = DocumentQualityGate().evaluate_course(
        plan=_plan(),
        draft=draft,
        section_chunks=((RetrievedChunk("ref:1", "Passage.", source, 1.0),),),
        sources=(source,),
    )

    assert any(issue.category == "metadata_contamination" for issue in report.blockers)


def test_raw_latex_like_math_outside_delimiters_is_blocked() -> None:
    report = _report((CourseBlock("text", "On travaille dans M_n(K) et C^k.", ("ref:1",)),))

    assert any(issue.category == "latex" for issue in report.blockers)


def test_valid_document_passes_quality_gate() -> None:
    report = _report((CourseBlock("text", "On travaille dans $M_n(K)$.", ("ref:1",)),))

    assert report.status == QualityStatus.PASS
    assert not report.blockers
