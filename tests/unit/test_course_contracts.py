"""Offline validation of course request and structured-generation contracts."""

import json

import pytest

from hermes_edu.application.ports.llm import ModelRequest, ModelResponse, ModelUsage
from hermes_edu.application.use_cases.create_course import CreateCourse, parse_course_value
from hermes_edu.domain.enums import Severity
from hermes_edu.domain.errors import GenerationError, SourceNotFoundError, ValidationError
from hermes_edu.domain.models.course import (
    CourseBlock,
    CourseDraft,
    CourseIssue,
    CoursePlan,
    CourseRequest,
    CourseSection,
    PlannedSection,
)
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.document import Artifact
from hermes_edu.domain.models.quality import QualityReport
from hermes_edu.domain.models.reference import (
    MAX_REFERENCE_QUERY_CHARS,
    MathChunk,
    ReferenceFilters,
    ReferenceHit,
    ReferenceSearchResult,
    SearchOutcome,
)
from hermes_edu.domain.models.source import RetrievedChunk, SourceReference


class ScriptedLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.tasks: list[str] = []
        self.requests: list[ModelRequest] = []

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        self.tasks.append(request.task)
        self.requests.append(request)
        return ModelResponse(self.responses.pop(0), ModelUsage("fake", "fixed", 1, 1, 0, 1, 0.0))


class Retriever:
    def retrieve(
        self, query: str, context: LearningContext, *, kind: str, top_k: int
    ) -> tuple[RetrievedChunk, ...]:
        return (
            RetrievedChunk(
                "official:0",
                "Official",
                SourceReference("official", "Official", "url", "public"),
                1.0,
            ),
        )


class References:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.purposes: list[str] = []
        self.top_ks: list[int | None] = []

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: ReferenceFilters | None = None,
        purpose: str = "",
    ) -> ReferenceSearchResult:
        self.queries.append(query)
        self.purposes.append(purpose)
        self.top_ks.append(top_k)
        return ReferenceSearchResult(SearchOutcome.NO_RELEVANT_SOURCE, query=query)


class HitReferences:
    def __init__(self, hits_by_purpose: dict[str, tuple[ReferenceHit, ...]]) -> None:
        self.hits_by_purpose = hits_by_purpose
        self.purposes: list[str] = []
        self.top_ks: list[int | None] = []

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: ReferenceFilters | None = None,
        purpose: str = "",
    ) -> ReferenceSearchResult:
        self.purposes.append(purpose)
        self.top_ks.append(top_k)
        return ReferenceSearchResult(
            SearchOutcome.ENOUGH_EVIDENCE,
            self.hits_by_purpose.get(purpose, ()),
            query,
        )


class Documents:
    def render(self, draft: object, sources: object, *, thread_id: str) -> Artifact:
        return Artifact("tex", "/tmp/course.tex", "a" * 64, 1)

    def compile(self, tex_artifact: Artifact) -> None:
        return None

    def repair_latex(self, tex_artifact: Artifact, diagnostic: str) -> Artifact:
        return tex_artifact

    def write_quality_report(
        self, report: QualityReport, *, thread_id: str
    ) -> tuple[Artifact, ...]:
        return (
            Artifact("quality_json", f"/tmp/{thread_id}-quality.json", "b" * 64, 1),
            Artifact("quality_md", f"/tmp/{thread_id}-quality.md", "c" * 64, 1),
        )


def _teaching_chunk(identifier: str = "reference:0") -> RetrievedChunk:
    return RetrievedChunk(
        identifier,
        "Passage pédagogique vérifié",
        SourceReference(identifier, "Cours", "p. 1", "local"),
        1.0,
    )


def _reference_hit(identifier: str, block_type: str, score: float) -> ReferenceHit:
    return ReferenceHit(
        MathChunk(
            chunk_id=identifier,
            document_id="doc",
            block_id=identifier,
            block_type=block_type,
            content=f"{block_type} vérifié",
            embedding_text=f"{block_type} vérifié",
            page_start=1,
            page_end=1,
        ),
        "Cours",
        score,
    )


def _service(llm: ScriptedLLM) -> CreateCourse:
    return CreateCourse(
        llm=llm,
        curriculum=Retriever(),
        references=References(),
        documents=Documents(),
        validate_text=lambda text: None,
        top_k=2,
        context_token_budget=500,
        max_output_tokens=500,
    )


def test_course_request_requires_curriculum_and_strict_section_count() -> None:
    with pytest.raises(ValidationError):
        CourseRequest("Intégrales", "", section_count=2)
    with pytest.raises(ValidationError):
        CourseRequest("Intégrales", "mp", section_count=0)

    plan = parse_course_value(
        '{"title":"Cours","sections":[{"title":"A","objective":"B"}]}', CoursePlan
    )
    assert len(plan.sections) == 1


def test_unknown_course_block_kind_reports_received_and_allowed_kinds() -> None:
    with pytest.raises(ValidationError) as captured:
        CourseBlock("axiom", "Énoncé.")

    assert str(captured.value) == (
        "Unknown course block kind 'axiom'. Allowed kinds: "
        "text, definition, theorem, proposition, lemma, corollary, result, "
        "proof, example, method, remark, exercise, solution"
    )


def test_plan_retries_then_rejects_wrong_section_count() -> None:
    wrong = '{"title":"Cours","sections":[{"title":"A","objective":"B"}]}'
    llm = ScriptedLLM([wrong, wrong])
    service = _service(llm)
    request = CourseRequest("Intégrales", "mp", section_count=2)

    with pytest.raises(GenerationError, match="twice"):
        service.plan(request, service.retrieve_curriculum(request))
    assert llm.tasks == ["plan", "plan"]


def test_plan_rejects_hallucinated_curriculum_ids_and_section_lookup_embeds_its_basis() -> None:
    invalid = json.dumps(
        {
            "title": "Cours",
            "sections": [
                {
                    "title": "A",
                    "objective": "B",
                    "curriculum_source_ids": ["invented"],
                }
            ],
        }
    )
    service = _service(ScriptedLLM([invalid, invalid]))
    request = CourseRequest("Intégrales", "mp", section_count=1)
    curriculum = service.retrieve_curriculum(request)

    with pytest.raises(GenerationError, match="allowed_curriculum_source_ids"):
        service.plan(request, curriculum)

    section = PlannedSection("Partie extraite", "Portée officielle", ("official:0",))
    references = References()
    service = CreateCourse(
        llm=ScriptedLLM([]),
        curriculum=Retriever(),
        references=references,
        documents=Documents(),
        validate_text=lambda text: None,
        top_k=2,
        context_token_budget=500,
        max_output_tokens=500,
    )
    with pytest.raises(SourceNotFoundError):
        service.retrieve_section(request, section, curriculum)
    assert references.queries == [
        "Intégrales\n\nPartie extraite\n\nPortée officielle\n\nOfficial",
        "Intégrales\n\nPartie extraite\n\nPortée officielle\n\nOfficial",
    ]
    assert references.purposes == ["", "example"]


def test_section_retrieval_merges_general_and_example_purpose_hits() -> None:
    theorem = _reference_hit("reference:theorem", "theorem", 0.9)
    example = _reference_hit("reference:example", "example", 0.8)
    references = HitReferences({"": (theorem,), "example": (example,)})
    service = CreateCourse(
        llm=ScriptedLLM([]),
        curriculum=Retriever(),
        references=references,
        documents=Documents(),
        validate_text=lambda text: None,
        top_k=3,
        example_top_k=4,
        context_token_budget=500,
        max_output_tokens=500,
    )

    hits = service.retrieve_section(
        CourseRequest("Intégrales", "mp", section_count=1),
        PlannedSection("Applications", "Construire des exemples", ("official:0",)),
        service.retrieve_curriculum(CourseRequest("Intégrales", "mp", section_count=1)),
    )

    assert references.purposes == ["", "example"]
    assert references.top_ks == [3, 4]
    assert [hit.chunk_id for hit in hits] == ["reference:theorem", "reference:example"]


def test_section_query_reserves_space_for_official_basis_when_plan_metadata_is_long() -> None:
    official_text = "PASSAGE OFFICIEL RETENU " + "x" * MAX_REFERENCE_QUERY_CHARS
    curriculum = (
        RetrievedChunk(
            "official:long",
            official_text,
            SourceReference("official", "Programme", "url", "public"),
            1.0,
        ),
    )
    references = References()
    service = CreateCourse(
        llm=ScriptedLLM([]),
        curriculum=Retriever(),
        references=references,
        documents=Documents(),
        validate_text=lambda text: None,
        top_k=2,
        context_token_budget=5000,
        max_output_tokens=500,
    )

    with pytest.raises(SourceNotFoundError):
        service.retrieve_section(
            CourseRequest("Intégrales", "mp"),
            PlannedSection("T" * 5000, "O" * 5000, ("official:long",)),
            curriculum,
        )

    assert len(references.queries[0]) <= MAX_REFERENCE_QUERY_CHARS
    assert "PASSAGE OFFICIEL RETENU" in references.queries[0]


def test_official_basis_is_separate_from_teaching_citations_and_budget() -> None:
    curriculum = (
        RetrievedChunk(
            "official:long",
            "PROGRAMME " + "x" * 4000,
            SourceReference("official", "Programme", "url", "public"),
            1.0,
        ),
    )
    teaching = (
        RetrievedChunk(
            "reference:1",
            "Référence pédagogique vérifiée.",
            SourceReference("reference:1", "Cours", "p. 1", "local"),
            1.0,
        ),
    )
    plan = CoursePlan("Cours", (PlannedSection("Partie", "Objectif", ("official:long",)),))
    grounded = json.dumps(
        {
            "title": "Partie",
            "blocks": [{"kind": "text", "text": "Contenu.", "source_ids": ["reference:1"]}],
            "source_ids": ["reference:1"],
        }
    )
    llm = ScriptedLLM([grounded])
    service = _service(llm)

    service.generate(CourseRequest("Sujet", "mp"), plan, 0, teaching, curriculum=curriculum)

    payload = json.loads(llm.requests[0].user)
    assert payload["allowed_source_ids"] == ["reference:1"]
    assert "PROGRAMME" in payload["official_curriculum_basis"]
    assert "Référence pédagogique vérifiée." in payload["sources"]


def test_generation_uses_llm_to_select_most_relevant_example_candidates() -> None:
    selection = json.dumps({"source_ids": ["reference:example-2", "reference:example-4"]})
    grounded = json.dumps(
        {
            "title": "Partie",
            "blocks": [
                {
                    "kind": "theorem",
                    "text": "Résultat sourcé.",
                    "source_ids": ["reference:theorem"],
                },
                {
                    "kind": "example",
                    "text": "Exemple choisi.",
                    "source_ids": ["reference:example-2"],
                },
            ],
            "source_ids": ["reference:theorem", "reference:example-2"],
        }
    )
    llm = ScriptedLLM([selection, grounded])
    service = _service(llm)
    request = CourseRequest("Sujet", "mp", section_count=1)
    plan = CoursePlan("Cours", (PlannedSection("Partie", "Objectif", ("official:0",)),))
    chunks = (
        RetrievedChunk(
            "reference:theorem",
            "Théorème vérifié.",
            SourceReference("reference:theorem", "Cours", "p. 1, type theorem", "local"),
            1.0,
        ),
        *(
            RetrievedChunk(
                f"reference:example-{index}",
                f"Exemple candidat {index}.",
                SourceReference(
                    f"reference:example-{index}",
                    "Cours",
                    f"p. {index + 1}, type example",
                    "local",
                ),
                1.0 - index / 10,
            )
            for index in range(1, 7)
        ),
    )

    section = service.generate(
        request,
        plan,
        0,
        chunks,
        curriculum=service.retrieve_curriculum(request),
    ).value

    assert llm.tasks == ["select_examples", "generate"]
    selection_payload = json.loads(llm.requests[0].user)
    assert selection_payload["candidate_example_source_ids"] == [
        "reference:example-1",
        "reference:example-2",
        "reference:example-3",
        "reference:example-4",
        "reference:example-5",
        "reference:example-6",
    ]
    generation_payload = json.loads(llm.requests[1].user)
    assert generation_payload["allowed_source_ids"] == [
        "reference:example-2",
        "reference:example-4",
        "reference:theorem",
    ]
    assert "Exemple candidat 2." in generation_payload["sources"]
    assert "Exemple candidat 1." not in generation_payload["sources"]
    assert section.source_ids == ("reference:theorem", "reference:example-2")


def test_official_curriculum_id_cannot_cite_a_course_block() -> None:
    curriculum = (
        RetrievedChunk(
            "official:1",
            "Programme",
            SourceReference("official", "Programme", "url", "public"),
            1.0,
        ),
    )
    teaching = (
        RetrievedChunk(
            "reference:1", "Cours", SourceReference("reference:1", "Cours", "p. 1", "local"), 1.0
        ),
    )
    plan = CoursePlan("Cours", (PlannedSection("Partie", "Objectif", ("official:1",)),))
    payload = json.dumps(
        {
            "title": "Partie",
            "blocks": [{"kind": "text", "text": "Contenu.", "source_ids": ["official:1"]}],
            "source_ids": ["official:1"],
        }
    )
    with pytest.raises(GenerationError, match="allowed_source_ids"):
        _service(ScriptedLLM([payload, payload])).generate(
            CourseRequest("Sujet", "mp"), plan, 0, teaching, curriculum=curriculum
        )

    with pytest.raises(SourceNotFoundError, match="curriculum basis"):
        _service(ScriptedLLM([])).generate(CourseRequest("Sujet", "mp"), plan, 0, teaching)
    with pytest.raises(ValidationError, match="must not overlap"):
        _service(ScriptedLLM([])).generate(
            CourseRequest("Sujet", "mp"), plan, 0, curriculum, curriculum=curriculum
        )
    other_official = RetrievedChunk(
        "official:2", "Autre partie du programme", curriculum[0].source, 1.0
    )
    with pytest.raises(ValidationError, match="must not overlap"):
        _service(ScriptedLLM([])).generate(
            CourseRequest("Sujet", "mp"),
            plan,
            0,
            (other_official,),
            curriculum=(*curriculum, other_official),
        )


def test_unknown_source_ids_and_malformed_json_retry_once_then_fail() -> None:
    unknown = json.dumps(
        {
            "title": "A",
            "blocks": [{"kind": "text", "text": "Texte valide."}],
            "source_ids": ["invented"],
        }
    )
    llm = ScriptedLLM([unknown, unknown])
    service = _service(llm)
    request = CourseRequest("Intégrales", "mp", section_count=1)
    plan = parse_course_value(
        '{"title":"Cours","sections":[{"title":"A","objective":"B"}]}', CoursePlan
    )
    sources = service.retrieve_curriculum(request)
    with pytest.raises(GenerationError, match="twice"):
        service.generate(request, plan, 0, (_teaching_chunk(),), curriculum=sources)
    assert llm.tasks == ["generate", "generate"]

    malformed = ScriptedLLM(["not-json", "still-not-json"])
    with pytest.raises(GenerationError, match="twice"):
        _service(malformed).plan(request, sources)
    assert malformed.tasks == ["plan", "plan"]


@pytest.mark.parametrize(
    "explanation",
    (
        "No defect here.",
        "This is not a mathematical error.",
        "There is no error.",
        "Ce n'est pas une erreur.",
        "Ce n\u2019est pas une erreur mathématique.",
        "Il n\u2019y a aucun défaut.",
        "Aucune erreur identifiée.",
        "Therefore, no defect.",
        "Therefore, return empty issues list.",
        "No error in domination. The example is correct.",
        "The proof is valid, so this is not a defect. No change required.",
    ),
)
def test_audit_filters_an_issue_that_concludes_no_defect(explanation: str) -> None:
    contradictory = json.dumps(
        {
            "issues": [
                {
                    "severity": "error",
                    "section_index": 1,
                    "section_title": "Fondements",
                    "explanation": explanation,
                }
            ]
        }
    )
    llm = ScriptedLLM([contradictory])
    course = CourseDraft(
        "Cours",
        (CourseSection("Fondements", (CourseBlock("text", "Contenu."),), ("official:0",)),),
    )
    service = _service(llm)

    if len(explanation) > 2000:
        with pytest.raises(GenerationError, match="explanation exceeds"):
            service.audit(
                CourseRequest("Intégrales", "mp", section_count=1),
                course,
                service.retrieve_curriculum(CourseRequest("Intégrales", "mp", section_count=1)),
                section_index=1,
            )
        assert llm.tasks == ["audit", "audit"]
        return

    result = service.audit(
        CourseRequest("Intégrales", "mp", section_count=1),
        course,
        service.retrieve_curriculum(CourseRequest("Intégrales", "mp", section_count=1)),
        section_index=1,
    )
    assert result.value == ()
    assert llm.tasks == ["audit"]


def test_audit_filters_no_defect_issues_but_preserves_actionable_errors() -> None:
    response = json.dumps(
        {
            "issues": [
                {
                    "severity": "warning",
                    "section_index": 1,
                    "section_title": "Fondements",
                    "explanation": "The statement is consistent.",
                },
                {
                    "severity": "error",
                    "section_index": 1,
                    "section_title": "Fondements",
                    "explanation": "The final majorant is not integrable at zero.",
                },
            ]
        }
    )
    service = _service(ScriptedLLM([response]))
    request = CourseRequest("Intégrales", "mp", section_count=1)
    course = CourseDraft(
        "Cours",
        (CourseSection("Fondements", (CourseBlock("text", "Contenu."),), ("official:0",)),),
    )

    result = service.audit(request, course, service.retrieve_curriculum(request), section_index=1)

    assert len(result.value) == 1
    assert result.value[0].explanation == "The final majorant is not integrable at zero."


def test_audit_rejects_a_too_long_explanation() -> None:
    too_long = json.dumps(
        {
            "issues": [
                {
                    "severity": "error",
                    "section_index": 1,
                    "section_title": "Fondements",
                    "explanation": "Tentative reasoning. " * 101,
                }
            ]
        }
    )
    llm = ScriptedLLM([too_long, too_long])
    service = _service(llm)
    request = CourseRequest("Intégrales", "mp", section_count=1)
    course = CourseDraft(
        "Cours",
        (CourseSection("Fondements", (CourseBlock("text", "Contenu."),), ("official:0",)),),
    )

    with pytest.raises(GenerationError, match="explanation exceeds"):
        service.audit(
            request,
            course,
            service.retrieve_curriculum(request),
            section_index=1,
        )

    assert llm.tasks == ["audit", "audit"]


def test_audit_filters_a_warning_that_concludes_no_defect() -> None:
    contradictory = json.dumps(
        {
            "issues": [
                {
                    "severity": "warning",
                    "section_index": 1,
                    "section_title": "Fondements",
                    "explanation": "The statement is consistent.",
                }
            ]
        }
    )
    llm = ScriptedLLM([contradictory])
    service = _service(llm)
    request = CourseRequest("Intégrales", "mp", section_count=1)
    course = CourseDraft(
        "Cours",
        (CourseSection("Fondements", (CourseBlock("text", "Contenu."),), ("official:0",)),),
    )

    result = service.audit(request, course, service.retrieve_curriculum(request), section_index=1)

    assert result.value == ()
    assert llm.tasks == ["audit"]


def test_audit_preserves_actionable_error_after_a_correct_step() -> None:
    explanation = "No defect here. However, the final majorant is not integrable at zero."
    response = json.dumps(
        {
            "issues": [
                {
                    "severity": "error",
                    "section_index": 1,
                    "section_title": "Fondements",
                    "explanation": explanation,
                }
            ]
        }
    )
    service = _service(ScriptedLLM([response]))
    request = CourseRequest("Intégrales", "mp", section_count=1)
    course = CourseDraft(
        "Cours",
        (CourseSection("Fondements", (CourseBlock("text", "Contenu."),), ("official:0",)),),
    )
    result = service.audit(request, course, service.retrieve_curriculum(request), section_index=1)
    assert len(result.value) == 1
    assert result.value[0].explanation == explanation


def test_generated_section_title_is_canonicalized_to_approved_plan() -> None:
    generated = json.dumps(
        {
            "title": "Titre reformulé par le modèle",
            "blocks": [{"kind": "text", "text": "Contenu valide.", "source_ids": ["reference:0"]}],
            "source_ids": ["reference:0"],
        }
    )
    llm = ScriptedLLM([generated])
    service = _service(llm)
    request = CourseRequest("Intégrales", "mp", section_count=1)
    plan = parse_course_value(
        '{"title":"Cours","sections":[{"title":"Titre approuvé","objective":"B"}]}',
        CoursePlan,
    )

    section = service.generate(
        request,
        plan,
        0,
        (_teaching_chunk(),),
        curriculum=service.retrieve_curriculum(request),
    ).value

    assert section.title == "Titre approuvé"
    assert llm.tasks == ["generate"]


def test_generation_rejects_ignoring_available_example_source() -> None:
    without_example = json.dumps(
        {
            "title": "A",
            "blocks": [
                {
                    "kind": "text",
                    "text": "Résultat expliqué sans exemple travaillé.",
                    "source_ids": ["reference:theorem"],
                }
            ],
            "source_ids": ["reference:theorem"],
        }
    )
    service = _service(
        ScriptedLLM(['{"source_ids":["reference:example"]}', without_example, without_example])
    )
    request = CourseRequest("Sujet", "mp", section_count=1)
    plan = parse_course_value(
        '{"title":"Cours","sections":[{"title":"A","objective":"B"}]}', CoursePlan
    )
    chunks = (
        RetrievedChunk(
            "reference:theorem",
            "Théorème vérifié.",
            SourceReference("reference:theorem", "Cours", "p. 1, type theorem", "local"),
            1.0,
        ),
        RetrievedChunk(
            "reference:example",
            "Exemple vérifié.",
            SourceReference("reference:example", "Cours", "p. 2, type example", "local"),
            0.9,
        ),
    )

    with pytest.raises(GenerationError, match="Available worked example sources"):
        service.generate(
            request,
            plan,
            0,
            chunks,
            curriculum=service.retrieve_curriculum(request),
        )


def test_audit_rejects_a_section_title_that_does_not_match_its_index() -> None:
    wrong_target = (
        '{"issues":[{"severity":"error","section_index":1,"section_title":"Méthodes",'
        '"explanation":"Justifier la domination"}]}'
    )
    llm = ScriptedLLM([wrong_target, wrong_target])
    service = _service(llm)
    request = CourseRequest("Intégrales", "mp", section_count=1)
    draft = CourseDraft(
        "Cours",
        (CourseSection("Fondements", (CourseBlock("text", "Contenu valide."),), ("official",)),),
    )

    with pytest.raises(GenerationError, match="audit JSON failed validation twice"):
        service.audit(request, draft, service.retrieve_curriculum(request))

    assert llm.tasks == ["audit", "audit"]


def test_missing_block_sources_inherit_valid_section_sources() -> None:
    payload = json.dumps(
        {
            "title": "A",
            "blocks": [{"kind": "theorem", "text": "Contenu.", "source_ids": []}],
            "source_ids": ["reference:0"],
        }
    )
    service = _service(ScriptedLLM([payload]))
    request = CourseRequest("Sujet", "mp", section_count=1)
    plan = parse_course_value(
        '{"title":"Cours","sections":[{"title":"A","objective":"B"}]}', CoursePlan
    )

    section = service.generate(
        request,
        plan,
        0,
        (_teaching_chunk(),),
        curriculum=service.retrieve_curriculum(request),
    ).value

    assert section.blocks[0].source_ids == ("reference:0",)


def test_unknown_block_sources_inherit_valid_section_sources() -> None:
    payload = json.dumps(
        {
            "title": "A",
            "blocks": [{"kind": "theorem", "text": "Contenu.", "source_ids": ["invented"]}],
            "source_ids": ["reference:0"],
        }
    )
    service = _service(ScriptedLLM([payload]))
    request = CourseRequest("Sujet", "mp", section_count=1)
    plan = parse_course_value(
        '{"title":"Cours","sections":[{"title":"A","objective":"B"}]}', CoursePlan
    )

    section = service.generate(
        request,
        plan,
        0,
        (_teaching_chunk(),),
        curriculum=service.retrieve_curriculum(request),
    ).value

    assert section.blocks[0].source_ids == ("reference:0",)


def test_generated_block_rejects_unknown_source_when_section_has_no_valid_source() -> None:
    payload = json.dumps(
        {
            "title": "A",
            "blocks": [{"kind": "theorem", "text": "Contenu.", "source_ids": ["invented"]}],
            "source_ids": ["invented"],
        }
    )
    service = _service(ScriptedLLM([payload, payload]))
    request = CourseRequest("Sujet", "mp", section_count=1)
    plan = parse_course_value(
        '{"title":"Cours","sections":[{"title":"A","objective":"B"}]}', CoursePlan
    )

    with pytest.raises(GenerationError, match="Every block"):
        service.generate(
            request,
            plan,
            0,
            (_teaching_chunk(),),
            curriculum=service.retrieve_curriculum(request),
        )


def test_revision_payload_instructs_deletion_of_unsupported_content() -> None:
    response = json.dumps(
        {
            "edits": [
                {
                    "block_index": 1,
                    "action": "delete",
                    "kind": "example",
                    "text": "",
                    "source_ids": [],
                }
            ]
        }
    )
    llm = ScriptedLLM([response])
    service = _service(llm)
    section = CourseSection(
        "Fondements",
        (
            CourseBlock("theorem", "Résultat sourcé.", ("reference:0",)),
            CourseBlock("example", "Exemple inventé.", ("reference:0",)),
        ),
        ("reference:0",),
    )
    issue = CourseIssue(
        Severity.ERROR,
        1,
        "Unsupported invented example absent from the reference; remove it.",
        "Fondements",
    )

    repaired = service.revise(section, (issue,), (_teaching_chunk(),)).value

    request = llm.requests[-1]
    payload = json.loads(request.user)
    assert request.task == "revise"
    assert "section" not in payload
    assert payload["focused_blocks"] == [
        {
            "block_index": 1,
            "kind": "example",
            "text": "Exemple inventé.",
            "source_ids": ["reference:0"],
        }
    ]
    assert payload["unsupported_content_policy"][0]["action"].startswith(
        "Delete unsupported or invented content"
    )
    assert "delete that example block" in request.system
    assert tuple(block.kind for block in repaired.blocks) == ("theorem",)


def test_section_bibliography_is_the_union_of_its_block_sources() -> None:
    payload = json.dumps(
        {
            "title": "A",
            "blocks": [
                {"kind": "theorem", "text": "Théorème.", "source_ids": ["theorem-source"]},
                {"kind": "example", "text": "Exemple.", "source_ids": ["example-source"]},
            ],
            "source_ids": ["example-source"],
        }
    )
    service = _service(ScriptedLLM([payload]))
    request = CourseRequest("Sujet", "mp", section_count=1)
    plan = parse_course_value(
        '{"title":"Cours","sections":[{"title":"A","objective":"B"}]}', CoursePlan
    )
    chunks = tuple(
        RetrievedChunk(
            identifier,
            "Passage vérifié",
            SourceReference(identifier, "Cours", "p. 1", "local"),
            1.0,
        )
        for identifier in ("theorem-source", "example-source")
    )
    section = service.generate(
        request,
        plan,
        0,
        chunks,
        curriculum=service.retrieve_curriculum(request),
    ).value
    assert section.source_ids == ("theorem-source", "example-source")
