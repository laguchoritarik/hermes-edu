"""Checkpointed course graph with section generation and bounded targeted repairs."""

# Nodes read keys guaranteed by their incoming edges; LangGraph has dynamic node typing.
# pyright: reportTypedDictNotRequiredAccess=false, reportUnknownMemberType=false

import json
from dataclasses import asdict, replace
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import TypeAdapter

from hermes_edu.application.services.structured_generation import StepResult
from hermes_edu.application.use_cases.adapt_course_wording import AdaptCourseWording
from hermes_edu.application.use_cases.create_course import CreateCourse
from hermes_edu.domain.enums import Severity
from hermes_edu.domain.errors import CompilationError, ValidationError
from hermes_edu.domain.models.course import (
    CourseDraft,
    CourseIssue,
    CoursePlan,
    CourseRequest,
    CourseSection,
)
from hermes_edu.domain.models.course_wording import CourseWordingPolicy
from hermes_edu.domain.models.source import RetrievedChunk, SourceReference
from hermes_edu.orchestration.state import (
    decode_artifact,
    decode_chunks,
    decode_usage,
    encode_artifact,
    encode_chunks,
    source_references,
)


class CourseState(TypedDict, total=False):
    workflow: str
    tex_only: bool
    approval_required: bool
    request_json: str
    thread_id: str
    curriculum_json: str
    plan_json: str
    approval: str
    sections_json: str
    section_chunks_json: str
    pending_chunks_json: str
    issues_json: str
    audit_cursor: int
    audit_target: int
    revisions: int
    usage_json: str
    draft_tex_json: str
    tex_json: str
    artifacts_json: str
    quality_report_json: str
    result_json: str
    wording_policy_json: str
    wording_source: str
    wording_sha256: str
    wording_cursor: int
    wording_pending_json: str
    wording_rejected: bool
    wording_blocked: bool
    latex_error: str
    latex_repairs: int
    audit_blocked: bool


def _usage[T](state: CourseState, result: StepResult[T]) -> str:
    return json.dumps(
        [
            asdict(usage)
            for usage in (
                *decode_usage(state.get("usage_json", "[]")),
                *result.additional_usages,
                result.usage,
            )
        ]
    )


def _sections(state: CourseState) -> tuple[CourseSection, ...]:
    return TypeAdapter(tuple[CourseSection, ...]).validate_json(state.get("sections_json", "[]"))


def _section_chunks(state: CourseState) -> tuple[tuple[RetrievedChunk, ...], ...]:
    return TypeAdapter(tuple[tuple[RetrievedChunk, ...], ...]).validate_json(
        state.get("section_chunks_json", "[]")
    )


def _issues(state: CourseState) -> tuple[CourseIssue, ...]:
    return TypeAdapter(tuple[CourseIssue, ...]).validate_json(state["issues_json"])


def _course_sources(chunks: tuple[RetrievedChunk, ...]) -> tuple[SourceReference, ...]:
    """Use passage identities for course citations, including official-programme passages."""
    return source_references(
        tuple(
            replace(chunk, source=replace(chunk.source, source_id=chunk.chunk_id))
            for chunk in chunks
        )
    )


def _cited_source_ids(state: CourseState, service: CreateCourse) -> set[str]:
    """Return only passage IDs that support the approved plan or rendered blocks."""
    plan = TypeAdapter(CoursePlan).validate_json(state["plan_json"])
    curriculum_ids = {
        source_id for section in plan.sections for source_id in section.curriculum_source_ids
    }
    if not curriculum_ids:
        # Match the bounded context used by legacy plans during section retrieval.
        curriculum = decode_chunks(state["curriculum_json"])
        curriculum_ids = {
            chunk.chunk_id
            for section in plan.sections
            for chunk in service.curriculum_basis(section, curriculum)
        }
    block_ids = {source_id for section in _sections(state) for source_id in section.source_ids}
    return curriculum_ids | block_ids


def build_course_graph(
    service: CreateCourse,
    *,
    approval_required: bool,
    max_revision_loops: int,
    max_latex_repair_loops: int = 1,
    wording: AdaptCourseWording | None = None,
) -> StateGraph[CourseState]:
    """Each completed section is durable; resume retries only the pending node."""
    graph = StateGraph(CourseState)

    def curriculum(state: CourseState) -> CourseState:
        request = TypeAdapter(CourseRequest).validate_json(state["request_json"])
        return {
            "workflow": "course",
            "approval_required": approval_required,
            "curriculum_json": encode_chunks(service.retrieve_curriculum(request)),
        }

    def plan(state: CourseState) -> CourseState:
        result = service.plan(
            TypeAdapter(CourseRequest).validate_json(state["request_json"]),
            decode_chunks(state["curriculum_json"]),
        )
        return {"plan_json": json.dumps(asdict(result.value)), "usage_json": _usage(state, result)}

    def review(state: CourseState) -> CourseState:
        if not approval_required:
            return {"approval": "approved"}
        response = interrupt(
            {"plan_json": state["plan_json"], "thread_id": state["thread_id"], "workflow": "course"}
        )
        if response not in {"approve", "reject"}:
            raise ValidationError("Approval response must be approve or reject")
        return {"approval": "approved" if response == "approve" else "rejected"}

    def retrieve(state: CourseState) -> CourseState:
        request = TypeAdapter(CourseRequest).validate_json(state["request_json"])
        current = (
            TypeAdapter(CoursePlan)
            .validate_json(state["plan_json"])
            .sections[len(_sections(state))]
        )
        curriculum = decode_chunks(state["curriculum_json"])
        hits = service.retrieve_section(request, current, curriculum)
        # Keep this checkpointed field teaching-only: its bounded context controls the
        # citations allowed in course blocks. Programme evidence stays in curriculum_json.
        return {"pending_chunks_json": encode_chunks(hits)}

    def generate(state: CourseState) -> CourseState:
        previous = _sections(state)
        chunks = decode_chunks(state["pending_chunks_json"])
        result = service.generate(
            TypeAdapter(CourseRequest).validate_json(state["request_json"]),
            TypeAdapter(CoursePlan).validate_json(state["plan_json"]),
            len(previous),
            chunks,
            curriculum=decode_chunks(state["curriculum_json"]),
        )
        return {
            "sections_json": json.dumps([asdict(section) for section in (*previous, result.value)]),
            "section_chunks_json": json.dumps(
                [[asdict(chunk) for chunk in group] for group in (*_section_chunks(state), chunks)]
            ),
            "usage_json": _usage(state, result),
        }

    def after_generate(state: CourseState) -> str:
        plan_value = TypeAdapter(CoursePlan).validate_json(state["plan_json"])
        return "retrieve" if len(_sections(state)) < len(plan_value.sections) else "render_draft"

    def draft(state: CourseState) -> CourseDraft:
        return CourseDraft(
            TypeAdapter(CoursePlan).validate_json(state["plan_json"]).title, _sections(state)
        )

    def render_course(state: CourseState):
        all_chunks = (
            *decode_chunks(state["curriculum_json"]),
            *(chunk for group in _section_chunks(state) for chunk in group),
        )
        cited = _cited_source_ids(state, service)
        sources = tuple(
            source for source in _course_sources(all_chunks) if source.source_id in cited
        )
        return service.render(draft(state), sources, thread_id=state["thread_id"])

    def render_draft(state: CourseState) -> CourseState:
        """Persist TeX for review without allowing a PDF before the audit succeeds."""
        return {"draft_tex_json": encode_artifact(render_course(state))}

    def audit(state: CourseState) -> CourseState:
        course = draft(state)
        target = state.get("audit_target", 0)
        cursor = state.get("audit_cursor", 0)
        plan = TypeAdapter(CoursePlan).validate_json(state["plan_json"])
        result = service.audit(
            TypeAdapter(CourseRequest).validate_json(state["request_json"]),
            course,
            service.curriculum_basis(
                plan.sections[target], decode_chunks(state["curriculum_json"])
            ),
            section_index=target + 1,
            verification=cursor >= len(course.sections),
            references=_section_chunks(state)[target],
        )
        previous = TypeAdapter(tuple[CourseIssue, ...]).validate_json(
            state.get("issues_json", "[]")
        )
        issues = (
            tuple(issue for issue in previous if issue.section_index != target + 1) + result.value
        )
        # Initial sweep checkpoints each section; after a repair only that section is re-audited.
        cursor = min(cursor + 1, len(course.sections))
        return {
            "issues_json": json.dumps([asdict(issue) for issue in issues]),
            "usage_json": _usage(state, result),
            "audit_cursor": cursor,
            "audit_target": cursor if cursor < len(course.sections) else target,
        }

    def after_audit(state: CourseState) -> str:
        if state.get("audit_cursor", 0) < len(_sections(state)):
            return "audit"
        if not any(issue.severity == Severity.ERROR for issue in _issues(state)):
            return "adapt_wording" if state.get("wording_policy_json") else "render"
        if state.get("revisions", 0) < max_revision_loops:
            return "revise"
        return "mark_audit_blocked"

    def revise(state: CourseState) -> CourseState:
        issues = _issues(state)
        index = next(
            issue.section_index - 1 for issue in issues if issue.severity == Severity.ERROR
        )
        sections = list(_sections(state))
        result = service.revise(
            sections[index],
            tuple(issue for issue in issues if issue.section_index == index + 1),
            _section_chunks(state)[index],
            candidate_offset=state.get("revisions", 0),
        )
        sections[index] = result.value
        return {
            "sections_json": json.dumps([asdict(section) for section in sections]),
            "revisions": state.get("revisions", 0) + 1,
            "audit_target": index,
            "usage_json": _usage(state, result),
        }

    def mark_audit_blocked(state: CourseState) -> CourseState:
        return {"audit_blocked": True}

    def adapt_wording(state: CourseState) -> CourseState:
        if wording is None:
            raise ValidationError("A wording service is required when a phrase file is supplied")
        policy = TypeAdapter(CourseWordingPolicy).validate_json(state["wording_policy_json"])
        index = state.get("wording_cursor", 0)
        sections = _sections(state)
        if index >= len(sections):
            return {}
        original = sections[index]
        if not any(block.kind in {"example", "solution"} for block in original.blocks):
            return {"wording_cursor": index + 1, "wording_pending_json": ""}
        result = wording.adapt(original, policy)
        return {
            "wording_pending_json": json.dumps(asdict(result.value)),
            "usage_json": _usage(state, result),
        }

    def after_wording(state: CourseState) -> str:
        if state.get("wording_rejected"):
            return "reject_wording"
        if state.get("wording_pending_json"):
            return "verify_wording"
        return (
            "adapt_wording" if state.get("wording_cursor", 0) < len(_sections(state)) else "render"
        )

    def after_audit_blocked(state: CourseState) -> str:
        return "adapt_wording" if state.get("wording_policy_json") else "render"

    def verify_wording(state: CourseState) -> CourseState:
        if wording is None:
            raise ValidationError("A wording service is required to verify transitions")
        index = state.get("wording_cursor", 0)
        sections = list(_sections(state))
        candidate = TypeAdapter(CourseSection).validate_json(state["wording_pending_json"])
        policy = TypeAdapter(CourseWordingPolicy).validate_json(state["wording_policy_json"])
        result = wording.verify(sections[index], candidate, policy)
        if not result.value:
            return {"wording_rejected": True, "usage_json": _usage(state, result)}
        sections[index] = candidate
        return {
            "sections_json": json.dumps([asdict(section) for section in sections]),
            "wording_cursor": index + 1,
            "wording_pending_json": "",
            "usage_json": _usage(state, result),
        }

    def reject_wording(state: CourseState) -> CourseState:
        return {
            "wording_blocked": True,
            "wording_pending_json": "",
            "wording_cursor": len(_sections(state)),
        }

    def render(state: CourseState) -> CourseState:
        # Re-render the final audited text over the draft TeX at the same workspace path.
        return {"tex_json": encode_artifact(render_course(state))}

    def compile_document(state: CourseState) -> CourseState:
        tex = decode_artifact(state["tex_json"])
        try:
            pdf = service.compile(tex)
        except CompilationError as exc:
            return {"latex_error": str(exc)}
        return {
            "latex_error": "",
            "artifacts_json": json.dumps(
                [asdict(artifact) for artifact in ((tex, pdf) if pdf else (tex,))]
            ),
        }

    def after_compile(state: CourseState) -> str:
        if not state.get("latex_error"):
            return "quality_gate"
        if state.get("latex_repairs", 0) < max_latex_repair_loops:
            return "repair_latex"
        return "latex_exhausted"

    def repair_latex(state: CourseState) -> CourseState:
        repaired = service.repair_latex(
            decode_artifact(state["tex_json"]),
            state["latex_error"],
        )
        return {
            "tex_json": encode_artifact(repaired),
            "latex_repairs": state.get("latex_repairs", 0) + 1,
            "latex_error": "",
        }

    def latex_exhausted(state: CourseState) -> CourseState:
        raise CompilationError(
            "Course LaTeX compilation failed after "
            f"{state.get('latex_repairs', 0)} deterministic repair attempt(s): "
            f"{state.get('latex_error', '')}"
        )

    def quality_gate(state: CourseState) -> CourseState:
        all_chunks = (
            *decode_chunks(state["curriculum_json"]),
            *(chunk for group in _section_chunks(state) for chunk in group),
        )
        cited = _cited_source_ids(state, service)
        sources = tuple(
            source for source in _course_sources(all_chunks) if source.source_id in cited
        )
        report = service.quality_report(
            plan=TypeAdapter(CoursePlan).validate_json(state["plan_json"]),
            draft=draft(state),
            section_chunks=_section_chunks(state),
            sources=sources,
        )
        report_artifacts = service.write_quality_report(report, thread_id=state["thread_id"])
        artifacts = TypeAdapter(tuple[dict[str, object], ...]).validate_json(
            state["artifacts_json"]
        )
        return {
            "quality_report_json": json.dumps(asdict(report), ensure_ascii=False),
            "artifacts_json": json.dumps(
                [*artifacts, *[asdict(item) for item in report_artifacts]]
            ),
        }

    def finish(state: CourseState) -> CourseState:
        usages = decode_usage(state.get("usage_json", "[]"))
        costs = [usage.estimated_cost_usd for usage in usages]
        wording_status = "not_requested"
        if state.get("wording_policy_json"):
            wording_status = "needs_revision" if state.get("wording_blocked") else "applied"
        all_chunks = (
            *decode_chunks(state["curriculum_json"]),
            *(chunk for group in _section_chunks(state) for chunk in group),
        )
        return {
            "result_json": json.dumps(
                {
                    "workflow": "course",
                    "thread_id": state["thread_id"],
                    "title": draft(state).title,
                    "sections": len(_sections(state)),
                    "artifacts": json.loads(state["artifacts_json"]),
                    "sources": [
                        asdict(source)
                        for source in _course_sources(all_chunks)
                        if source.source_id in _cited_source_ids(state, service)
                    ],
                    "audit_issues": [asdict(issue) for issue in _issues(state)],
                    "audit_status": "needs_revision" if state.get("audit_blocked") else "passed",
                    "quality_status": json.loads(state["quality_report_json"])["status"],
                    "quality_report": json.loads(state["quality_report_json"]),
                    "revisions": state.get("revisions", 0),
                    "latex_repairs": state.get("latex_repairs", 0),
                    "wording": {
                        "source": state.get("wording_source"),
                        "sha256": state.get("wording_sha256"),
                        "sections_processed": state.get("wording_cursor", 0),
                        "status": wording_status,
                    },
                    "input_tokens": sum(usage.input_tokens for usage in usages),
                    "output_tokens": sum(usage.output_tokens for usage in usages),
                    "cached_tokens": sum(usage.cached_tokens for usage in usages),
                    "estimated_cost_usd": sum(cost for cost in costs if cost is not None)
                    if all(cost is not None for cost in costs)
                    else None,
                    "usage": [asdict(usage) for usage in usages],
                },
                ensure_ascii=False,
            )
        }

    for name, node in [
        ("curriculum", curriculum),
        ("plan", plan),
        ("review", review),
        ("retrieve", retrieve),
        ("generate", generate),
        ("render_draft", render_draft),
        ("audit", audit),
        ("revise", revise),
        ("mark_audit_blocked", mark_audit_blocked),
        ("adapt_wording", adapt_wording),
        ("verify_wording", verify_wording),
        ("reject_wording", reject_wording),
        ("render", render),
        ("compile", compile_document),
        ("quality_gate", quality_gate),
        ("repair_latex", repair_latex),
        ("latex_exhausted", latex_exhausted),
        ("finish", finish),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "curriculum")
    graph.add_edge("curriculum", "plan")
    graph.add_edge("plan", "review")

    def after_review(state: CourseState) -> str:
        return "retrieve" if state["approval"] == "approved" else END

    graph.add_conditional_edges("review", after_review, {"retrieve": "retrieve", END: END})
    graph.add_edge("retrieve", "generate")
    graph.add_conditional_edges(
        "generate", after_generate, {"retrieve": "retrieve", "render_draft": "render_draft"}
    )
    graph.add_edge("render_draft", "audit")
    graph.add_conditional_edges(
        "audit",
        after_audit,
        {
            "audit": "audit",
            "render": "render",
            "revise": "revise",
            "mark_audit_blocked": "mark_audit_blocked",
            "adapt_wording": "adapt_wording",
        },
    )
    graph.add_edge("revise", "audit")
    graph.add_edge("reject_wording", "render")
    graph.add_conditional_edges(
        "mark_audit_blocked",
        after_audit_blocked,
        {"adapt_wording": "adapt_wording", "render": "render"},
    )
    for node in ("adapt_wording", "verify_wording"):
        graph.add_conditional_edges(
            node,
            after_wording,
            {
                "adapt_wording": "adapt_wording",
                "verify_wording": "verify_wording",
                "reject_wording": "reject_wording",
                "render": "render",
            },
        )
    graph.add_edge("render", "compile")
    graph.add_conditional_edges(
        "compile",
        after_compile,
        {
            "finish": "finish",
            "quality_gate": "quality_gate",
            "repair_latex": "repair_latex",
            "latex_exhausted": "latex_exhausted",
        },
    )
    graph.add_edge("quality_gate", "finish")
    graph.add_edge("repair_latex", "compile")
    graph.add_edge("finish", END)
    return graph
