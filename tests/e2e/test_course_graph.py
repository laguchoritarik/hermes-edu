"""Offline course workflow tests, including durable section checkpoints and review."""

# Third-party LangGraph configuration stubs are less specific than its runtime values.
# pyright: reportUnknownMemberType=false

import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph
from langgraph.types import Command

from hermes_edu.application.ports.llm import ModelRequest, ModelResponse, ModelUsage
from hermes_edu.application.use_cases.adapt_course_wording import AdaptCourseWording
from hermes_edu.application.use_cases.create_course import CreateCourse
from hermes_edu.domain.errors import (
    CompilationError,
    GenerationError,
    SourceNotFoundError,
)
from hermes_edu.domain.models.course import CourseRequest
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.document import Artifact
from hermes_edu.domain.models.quality import QualityReport
from hermes_edu.domain.models.reference import (
    MathChunk,
    ReferenceHit,
    ReferenceSearchResult,
    SearchOutcome,
)
from hermes_edu.domain.models.source import RetrievedChunk, SourceReference
from hermes_edu.orchestration.graphs.course import CourseState, build_course_graph


class ScriptedLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.tasks: list[str] = []
        self.requests: list[ModelRequest] = []

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        self.tasks.append(request.task)
        self.requests.append(request)
        return ModelResponse(self.responses.pop(0), ModelUsage("fake", "fixed", 10, 5, 0, 1, 0.001))


class CurriculumRetriever:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls: list[tuple[str, LearningContext, str, int]] = []
        self.chunks: tuple[RetrievedChunk, ...] = ()

    def retrieve(
        self, query: str, context: LearningContext, *, kind: str, top_k: int
    ) -> tuple[RetrievedChunk, ...]:
        self.calls.append((query, context, kind, top_k))
        if not self.available:
            return ()
        if self.chunks:
            return self.chunks
        return (
            RetrievedChunk(
                "official:0",
                "Programme officiel : intégrales dépendant d'un paramètre.",
                SourceReference(
                    "official", "Programme officiel", "https://education.example/mp", "public"
                ),
                1.0,
            ),
        )


class TeachingReferences:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls: list[str] = []
        self.purposes: list[str] = []

    def search(
        self, query: str, *, top_k: int | None = None, purpose: str = "", **_: object
    ) -> ReferenceSearchResult:
        self.calls.append(query)
        self.purposes.append(purpose)
        if not self.available:
            return ReferenceSearchResult(SearchOutcome.NO_RELEVANT_SOURCE, query=query)
        section_id = "ref-a:0" if "Fondements" in query else "ref-b:0"
        return ReferenceSearchResult(
            SearchOutcome.ENOUGH_EVIDENCE,
            (
                ReferenceHit(
                    MathChunk(
                        section_id,
                        "reference",
                        section_id,
                        "text",
                        section_id,
                        section_id,
                        1,
                        1,
                        section="Cours",
                    ),
                    "Cours d'intégration",
                    0.9,
                ),
            ),
            query,
        )


class FakeDocuments:
    def render(self, draft: object, sources: object, *, thread_id: str) -> Artifact:
        return Artifact("tex", f"/tmp/{thread_id}.tex", "a" * 64, 100)

    def compile(self, tex_artifact: Artifact) -> Artifact:
        return Artifact("pdf", tex_artifact.path.replace(".tex", ".pdf"), "b" * 64, 200)

    def repair_latex(self, tex_artifact: Artifact, diagnostic: str) -> Artifact:
        return tex_artifact

    def write_quality_report(
        self, report: QualityReport, *, thread_id: str
    ) -> tuple[Artifact, ...]:
        return (
            Artifact("quality_json", f"/tmp/{thread_id}-quality.json", "c" * 64, 10),
            Artifact("quality_md", f"/tmp/{thread_id}-quality.md", "d" * 64, 10),
        )


class RepairingDocuments(FakeDocuments):
    def __init__(self) -> None:
        self.compile_calls = 0
        self.repair_calls: list[str] = []

    def compile(self, tex_artifact: Artifact) -> Artifact:
        self.compile_calls += 1
        if self.compile_calls == 1:
            raise CompilationError(
                "XeLaTeX exited 1: ./course.tex:7: Undefined control sequence.\n"
                "l.7 Texte \\badmacro."
            )
        return super().compile(tex_artifact)

    def repair_latex(self, tex_artifact: Artifact, diagnostic: str) -> Artifact:
        self.repair_calls.append(diagnostic)
        return Artifact("tex", tex_artifact.path, "c" * 64, tex_artifact.size_bytes + 1)


PLAN = json.dumps(
    {
        "title": "Intégrales à paramètre",
        "sections": [
            {
                "title": "Fondements",
                "objective": "Poser les définitions",
                "curriculum_source_ids": ["official:0"],
            },
            {
                "title": "Méthodes",
                "objective": "Justifier les passages",
                "curriculum_source_ids": ["official:0"],
            },
        ],
    }
)
SECTION_A = json.dumps(
    {
        "title": "Fondements",
        "blocks": [
            {
                "kind": "definition",
                "text": "On définit une intégrale paramétrée.",
                "source_ids": ["ref-a:0"],
            }
        ],
        "source_ids": ["ref-a:0"],
    }
)
SECTION_B = json.dumps(
    {
        "title": "Méthodes",
        "blocks": [
            {
                "kind": "method",
                "text": "Une domination justifie le passage.",
                "source_ids": ["ref-b:0"],
            }
        ],
        "source_ids": ["ref-b:0"],
    }
)
REPAIRED_A = json.dumps(
    {
        "title": "Fondements",
        "blocks": [
            {
                "kind": "definition",
                "text": "La domination est explicitement vérifiée.",
                "source_ids": ["ref-a:0"],
            }
        ],
        "source_ids": ["ref-a:0"],
    }
)
PASS = '{"issues":[]}'
FAIL_A = (
    '{"issues":[{"severity":"error","section_index":1,"section_title":"Fondements",'
    '"explanation":"Justifier la domination"}]}'
)
FAIL_B = (
    '{"issues":[{"severity":"error","section_index":2,"section_title":"Méthodes",'
    '"explanation":"Contrôler la majoration"}]}'
)
WRONG_AUDIT_TARGET = (
    '{"issues":[{"severity":"error","section_index":1,"section_title":"Méthodes",'
    '"explanation":"Justifier la domination"}]}'
)


def _graph(
    tmp_path: Path,
    llm: ScriptedLLM,
    *,
    approval: bool = False,
    revisions: int = 2,
    curriculum_available: bool = True,
    references_available: bool = True,
    documents: FakeDocuments | None = None,
    latex_repairs: int = 1,
) -> tuple[StateGraph[CourseState], CurriculumRetriever, TeachingReferences]:
    curriculum = CurriculumRetriever(curriculum_available)
    references = TeachingReferences(references_available)
    service = CreateCourse(
        llm=llm,
        curriculum=curriculum,
        references=references,
        documents=documents or FakeDocuments(),
        validate_text=lambda text: None,
        top_k=2,
        context_token_budget=500,
        max_output_tokens=500,
    )
    return (
        build_course_graph(
            service,
            approval_required=approval,
            max_revision_loops=revisions,
            max_latex_repair_loops=latex_repairs,
            wording=AdaptCourseWording(llm, max_output_tokens=500),
        ),
        curriculum,
        references,
    )


def _input(thread_id: str) -> CourseState:
    return {
        "request_json": json.dumps(
            asdict(CourseRequest("Intégrales à paramètre", "mp-officiel", section_count=2))
        ),
        "thread_id": thread_id,
    }


def test_two_sections_retrieve_independently_and_account_usage(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, SECTION_A, SECTION_B, PASS, PASS])
    builder, curriculum, references = _graph(tmp_path, llm)
    with SqliteSaver.from_conn_string(str(tmp_path / "course.db")) as saver:
        graph = builder.compile(checkpointer=saver)
        state = graph.invoke(
            _input("two-sections"), config={"configurable": {"thread_id": "two-sections"}}
        )

    result = json.loads(state["result_json"])
    assert result["sections"] == 2
    assert result["input_tokens"] == 50
    assert result["revisions"] == 0
    assert [artifact["kind"] for artifact in result["artifacts"]] == [
        "tex",
        "pdf",
        "quality_json",
        "quality_md",
    ]
    assert result["quality_status"] == "PASS"
    assert [source["source_id"] for source in result["sources"]] == [
        "official:0",
        "ref-a:0",
        "ref-b:0",
    ]
    assert curriculum.calls == [
        ("Intégrales à paramètre", LearningContext("mp-officiel", "MP"), "curriculum", 2)
    ]
    assert len(references.calls) == 4
    assert references.purposes == ["", "example", "", "example"]
    assert "Fondements" in references.calls[0]
    assert "Méthodes" in references.calls[2]
    assert all(
        "Programme officiel : intégrales dépendant d'un paramètre." in call
        for call in references.calls
    )
    assert llm.tasks == ["plan", "generate", "generate", "audit", "audit"]
    audit_payloads = [
        json.loads(request.user) for request in llm.requests if request.task == "audit"
    ]
    assert [payload["selected_section_index"] for payload in audit_payloads] == [1, 2]
    assert [len(payload["draft"]["sections"]) for payload in audit_payloads] == [1, 1]
    assert audit_payloads[0]["draft"]["sections"][0]["title"] == "Fondements"
    assert audit_payloads[1]["draft"]["sections"][0]["title"] == "Méthodes"


def test_audit_receives_only_the_current_section_curriculum_basis(tmp_path: Path) -> None:
    plan = json.dumps(
        {
            "title": "Intégrales à paramètre",
            "sections": [
                {
                    "title": "Fondements",
                    "objective": "Poser les définitions",
                    "curriculum_source_ids": ["official:early"],
                },
                {
                    "title": "Méthodes",
                    "objective": "Justifier les passages",
                    "curriculum_source_ids": ["official:late"],
                },
            ],
        }
    )
    llm = ScriptedLLM([plan, SECTION_A, SECTION_B, PASS, PASS])
    builder, curriculum, _ = _graph(tmp_path, llm)
    curriculum.chunks = (
        RetrievedChunk(
            "official:early",
            "PROGRAMME PREMIERE PARTIE",
            SourceReference("official", "Programme", "url", "public"),
            1.0,
        ),
        RetrievedChunk(
            "official:late",
            "PROGRAMME SECONDE PARTIE",
            SourceReference("official", "Programme", "url", "public"),
            1.0,
        ),
    )
    with SqliteSaver.from_conn_string(str(tmp_path / "basis-audit.db")) as saver:
        builder.compile(checkpointer=saver).invoke(
            _input("basis-audit"), config={"configurable": {"thread_id": "basis-audit"}}
        )

    audits = [json.loads(request.user) for request in llm.requests if request.task == "audit"]
    assert "PROGRAMME PREMIERE PARTIE" in audits[0]["official_curriculum"]
    assert "PROGRAMME SECONDE PARTIE" not in audits[0]["official_curriculum"]
    assert "PROGRAMME SECONDE PARTIE" in audits[1]["official_curriculum"]
    assert "PROGRAMME PREMIERE PARTIE" not in audits[1]["official_curriculum"]


def test_targeted_repair_and_audit_exhaustion_are_bounded(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, SECTION_A, SECTION_B, FAIL_A, PASS, REPAIRED_A, PASS])
    builder, _, _ = _graph(tmp_path, llm, revisions=1)
    with SqliteSaver.from_conn_string(str(tmp_path / "repair.db")) as saver:
        state = builder.compile(checkpointer=saver).invoke(
            _input("repair"), config={"configurable": {"thread_id": "repair"}}
        )
    assert json.loads(state["result_json"])["revisions"] == 1
    assert llm.tasks == ["plan", "generate", "generate", "audit", "audit", "revise", "verify"]

    exhausted = ScriptedLLM([PLAN, SECTION_A, SECTION_B, FAIL_A, PASS])
    builder, _, _ = _graph(tmp_path, exhausted, revisions=0)
    with SqliteSaver.from_conn_string(str(tmp_path / "exhausted.db")) as saver:
        state = builder.compile(checkpointer=saver).invoke(
            _input("exhaust"), config={"configurable": {"thread_id": "exhaust"}}
        )
    result = json.loads(state["result_json"])
    assert result["audit_status"] == "needs_revision"
    assert result["audit_issues"][0]["explanation"] == "Justifier la domination"
    assert [artifact["kind"] for artifact in result["artifacts"]] == [
        "tex",
        "pdf",
        "quality_json",
        "quality_md",
    ]
    assert exhausted.tasks == ["plan", "generate", "generate", "audit", "audit"]


def test_failed_audit_keeps_issues_and_still_compiles_pdf(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, SECTION_A, SECTION_B, FAIL_A, PASS])
    builder, _, _ = _graph(tmp_path, llm, revisions=0)
    config: RunnableConfig = {"configurable": {"thread_id": "draft-before-audit"}}
    with SqliteSaver.from_conn_string(str(tmp_path / "draft-before-audit.db")) as saver:
        graph = builder.compile(checkpointer=saver)
        state = graph.invoke(_input("draft-before-audit"), config=config)
        snapshot = graph.get_state(config)

    result = json.loads(state["result_json"])
    assert result["audit_status"] == "needs_revision"
    assert result["audit_issues"][0]["explanation"] == "Justifier la domination"
    draft_tex = json.loads(snapshot.values["draft_tex_json"])
    assert draft_tex["kind"] == "tex"
    assert draft_tex["path"] == "/tmp/draft-before-audit.tex"
    assert [artifact["kind"] for artifact in result["artifacts"]] == [
        "tex",
        "pdf",
        "quality_json",
        "quality_md",
    ]


def test_latex_compile_failure_uses_bounded_deterministic_repair(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, SECTION_A, SECTION_B, PASS, PASS])
    documents = RepairingDocuments()
    builder, _, _ = _graph(tmp_path, llm, documents=documents, latex_repairs=1)

    with SqliteSaver.from_conn_string(str(tmp_path / "latex-repair.db")) as saver:
        state = builder.compile(checkpointer=saver).invoke(
            _input("latex-repair"), config={"configurable": {"thread_id": "latex-repair"}}
        )

    result = json.loads(state["result_json"])
    assert result["latex_repairs"] == 1
    assert documents.compile_calls == 2
    assert len(documents.repair_calls) == 1


def test_latex_compile_failure_stops_after_repair_budget(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, SECTION_A, SECTION_B, PASS, PASS])
    documents = RepairingDocuments()
    builder, _, _ = _graph(tmp_path, llm, documents=documents, latex_repairs=0)

    with (
        SqliteSaver.from_conn_string(str(tmp_path / "latex-exhausted.db")) as saver,
        pytest.raises(CompilationError, match="deterministic repair"),
    ):
        builder.compile(checkpointer=saver).invoke(
            _input("latex-exhausted"),
            config={"configurable": {"thread_id": "latex-exhausted"}},
        )

    assert documents.compile_calls == 1
    assert documents.repair_calls == []


def test_approval_persists_for_resume_and_rejection_stops(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, SECTION_A, SECTION_B, PASS, PASS])
    builder, _, _ = _graph(tmp_path, llm, approval=True)
    config: RunnableConfig = {"configurable": {"thread_id": "approval"}}
    with SqliteSaver.from_conn_string(str(tmp_path / "approval.db")) as saver:
        graph = builder.compile(checkpointer=saver)
        paused = graph.invoke(_input("approval"), config=config)
        assert "__interrupt__" in paused
        assert llm.tasks == ["plan"]
    with SqliteSaver.from_conn_string(str(tmp_path / "approval.db")) as saver:
        state = builder.compile(checkpointer=saver).invoke(Command(resume="approve"), config=config)
    assert json.loads(state["result_json"])["sections"] == 2
    assert llm.tasks == ["plan", "generate", "generate", "audit", "audit"]

    rejected = ScriptedLLM([PLAN])
    builder, _, _ = _graph(tmp_path, rejected, approval=True)
    config = {"configurable": {"thread_id": "reject"}}
    with SqliteSaver.from_conn_string(str(tmp_path / "reject.db")) as saver:
        graph = builder.compile(checkpointer=saver)
        assert "__interrupt__" in graph.invoke(_input("reject"), config=config)
        state = graph.invoke(Command(resume="reject"), config=config)
    assert "result_json" not in state
    assert rejected.tasks == ["plan"]


def test_untrusted_state_cannot_bypass_required_approval(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN])
    builder, _, _ = _graph(tmp_path, llm, approval=True)
    untrusted_input = cast(CourseState, {**_input("bypass"), "skip_approval": True})
    with SqliteSaver.from_conn_string(str(tmp_path / "bypass.db")) as saver:
        paused = builder.compile(checkpointer=saver).invoke(
            untrusted_input, config={"configurable": {"thread_id": "bypass"}}
        )

    assert "__interrupt__" in paused
    assert llm.tasks == ["plan"]


def test_reopens_after_second_section_failure_without_regenerating_first(tmp_path: Path) -> None:
    failed_llm = ScriptedLLM([PLAN, SECTION_A, "not-json", "still-not-json"])
    builder, first_curriculum, first_references = _graph(tmp_path, failed_llm)
    config: RunnableConfig = {"configurable": {"thread_id": "recover"}}
    checkpoint_path = tmp_path / "recover.db"
    with (
        SqliteSaver.from_conn_string(str(checkpoint_path)) as saver,
        pytest.raises(GenerationError, match="generate JSON failed validation twice"),
    ):
        builder.compile(checkpointer=saver).invoke(_input("recover"), config=config)
    assert failed_llm.tasks == ["plan", "generate", "generate", "generate"]
    assert len(first_curriculum.calls) == 1
    assert len(first_references.calls) == 4
    assert first_references.purposes == ["", "example", "", "example"]

    resumed_llm = ScriptedLLM([SECTION_B, PASS, PASS])
    resumed_builder, resumed_curriculum, resumed_references = _graph(tmp_path, resumed_llm)
    with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
        state = resumed_builder.compile(checkpointer=saver).invoke(None, config=config)

    assert json.loads(state["result_json"])["sections"] == 2
    assert resumed_llm.tasks == ["generate", "audit", "audit"]
    assert resumed_curriculum.calls == []
    assert resumed_references.calls == []


def test_retains_other_section_error_across_scoped_reaudit_and_repairs_both(tmp_path: Path) -> None:
    llm = ScriptedLLM(
        [PLAN, SECTION_A, SECTION_B, FAIL_A, FAIL_B, REPAIRED_A, PASS, SECTION_B, PASS]
    )
    builder, _, _ = _graph(tmp_path, llm, revisions=2)
    with SqliteSaver.from_conn_string(str(tmp_path / "two-errors.db")) as saver:
        state = builder.compile(checkpointer=saver).invoke(
            _input("two-errors"), config={"configurable": {"thread_id": "two-errors"}}
        )

    result = json.loads(state["result_json"])
    assert result["revisions"] == 2
    assert result["audit_issues"] == []
    assert llm.tasks == [
        "plan",
        "generate",
        "generate",
        "audit",
        "audit",
        "revise",
        "verify",
        "revise",
        "verify",
    ]


def test_wrong_audit_section_title_fails_before_revision_budget_is_used(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, SECTION_A, SECTION_B, WRONG_AUDIT_TARGET, WRONG_AUDIT_TARGET])
    builder, _, _ = _graph(tmp_path, llm, revisions=1)
    with (
        SqliteSaver.from_conn_string(str(tmp_path / "wrong-audit.db")) as saver,
        pytest.raises(GenerationError, match="audit JSON failed validation twice"),
    ):
        builder.compile(checkpointer=saver).invoke(
            _input("wrong-audit"), config={"configurable": {"thread_id": "wrong-audit"}}
        )

    assert llm.tasks == ["plan", "generate", "generate", "audit", "audit"]


@pytest.mark.parametrize(
    "curriculum_available,references_available", [(False, True), (True, False)]
)
def test_missing_curriculum_or_references_stop_before_generation(
    tmp_path: Path, curriculum_available: bool, references_available: bool
) -> None:
    llm = ScriptedLLM([PLAN])
    builder, _, _ = _graph(
        tmp_path,
        llm,
        curriculum_available=curriculum_available,
        references_available=references_available,
    )
    with (
        SqliteSaver.from_conn_string(str(tmp_path / "missing.db")) as saver,
        pytest.raises(SourceNotFoundError),
    ):
        builder.compile(checkpointer=saver).invoke(
            _input("missing"), config={"configurable": {"thread_id": "missing"}}
        )
    assert llm.tasks == ([] if not curriculum_available else ["plan"])


def test_wording_verification_failure_is_durable_and_never_renders(tmp_path: Path) -> None:
    section = json.loads(SECTION_A)
    section["blocks"][0].update(kind="example", text="Par conséquent, $x=y$ et $x\\leq y$.")
    adapted = {
        "status": "apply",
        "edits": [
            {
                "block_index": 0,
                "start": 0,
                "end": 14,
                "original": "Par conséquent",
                "phrase_index": 0,
                "is_transition": True,
            }
        ],
    }

    class UnavailableVerification(ScriptedLLM):
        def complete_json(self, request: ModelRequest) -> ModelResponse:
            if request.task == "verify":
                self.tasks.append(request.task)
                raise GenerationError("Verification provider unavailable")
            return super().complete_json(request)

    llm = UnavailableVerification(
        [PLAN, json.dumps(section), SECTION_B, PASS, PASS, json.dumps(adapted)]
    )
    builder, _, _ = _graph(tmp_path, llm)
    config: RunnableConfig = {"configurable": {"thread_id": "wording"}}
    request = _input("wording")
    request["wording_policy_json"] = '{"phrases":["Donc"]}'
    checkpoint = str(tmp_path / "wording.db")
    with SqliteSaver.from_conn_string(checkpoint) as saver:
        graph = builder.compile(checkpointer=saver)
        with pytest.raises(GenerationError, match="provider unavailable"):
            graph.invoke(request, config=config)
        snapshot = graph.get_state(config)
        assert "tex_json" not in snapshot.values
        assert snapshot.next == ("verify_wording",)
        assert json.loads(snapshot.values["sections_json"])[0]["blocks"][0]["text"].startswith(
            "Par conséquent"
        )
        assert json.loads(snapshot.values["wording_pending_json"])["blocks"][0]["text"].startswith(
            "Donc"
        )
    resumed = ScriptedLLM(
        ['{"faithful":true,"reason":"Même déduction, aucune autre modification"}']
    )
    builder, _, _ = _graph(tmp_path, resumed)
    with SqliteSaver.from_conn_string(checkpoint) as saver:
        state = builder.compile(checkpointer=saver).invoke(None, config=config)
    assert resumed.tasks == ["verify"]
    assert llm.tasks[-2:] == ["wording", "verify"]
    assert (
        json.loads(state["sections_json"])[0]["blocks"][0]["text"] == "Donc, $x=y$ et $x\\leq y$."
    )
    assert state["wording_cursor"] == 2
    assert "result_json" in state


def test_no_change_wording_still_requires_closed_list_verification(tmp_path: Path) -> None:
    section = json.loads(SECTION_A)
    section["blocks"][0].update(kind="solution", text="Par conséquent, $x=y$.")
    llm = ScriptedLLM(
        [
            PLAN,
            json.dumps(section),
            SECTION_B,
            PASS,
            PASS,
            '{"status":"no_change"}',
            '{"faithful":false,"reason":"Une liaison reste hors liste"}',
        ]
    )
    builder, _, _ = _graph(tmp_path, llm)
    request = _input("no-change")
    request["wording_policy_json"] = '{"phrases":["Donc"]}'
    with SqliteSaver.from_conn_string(str(tmp_path / "no-change.db")) as saver:
        graph = builder.compile(checkpointer=saver)
        config: RunnableConfig = {"configurable": {"thread_id": "no-change"}}
        state = graph.invoke(request, config=config)
        snapshot = graph.get_state(config)
        result = json.loads(state["result_json"])
        assert result["wording"]["status"] == "needs_revision"
        assert snapshot.values["wording_rejected"] is True
        assert [artifact["kind"] for artifact in result["artifacts"]] == [
            "tex",
            "pdf",
            "quality_json",
            "quality_md",
        ]
