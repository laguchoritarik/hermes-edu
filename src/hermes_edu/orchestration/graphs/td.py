"""Checkpointable TD subgraph with bounded revision and plan approval."""

# LangGraph's dynamic node overloads and progressive state keys are wider than its static stubs.
# pyright: reportTypedDictNotRequiredAccess=false, reportUnknownMemberType=false

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from hermes_edu.application.use_cases.create_td import CreateTD
from hermes_edu.domain.enums import Severity
from hermes_edu.domain.errors import AuditExhaustedError, ValidationError
from hermes_edu.orchestration.state import (
    TDState,
    append_usage,
    decode_artifact,
    decode_chunks,
    decode_draft,
    decode_issues,
    decode_plan,
    decode_request,
    encode_artifact,
    encode_artifacts,
    encode_chunks,
    encode_draft,
    encode_issues,
    encode_plan,
    encode_result,
    source_references,
    summarize_result,
)


def build_td_graph(
    service: CreateTD, *, approval_required: bool, max_revision_loops: int
) -> StateGraph[TDState]:
    """Build the reusable TD subgraph; the main graph owns its checkpointer."""
    graph = StateGraph(TDState)

    def curriculum(state: TDState) -> TDState:
        chunks = service.retrieve_curriculum(decode_request(state["request_json"]))
        return {"curriculum_json": encode_chunks(chunks)}

    def knowledge(state: TDState) -> TDState:
        chunks = service.retrieve_knowledge(decode_request(state["request_json"]))
        return {"knowledge_json": encode_chunks(chunks)}

    def plan(state: TDState) -> TDState:
        chunks = decode_chunks(state["curriculum_json"]) + decode_chunks(state["knowledge_json"])
        result = service.plan(decode_request(state["request_json"]), chunks)
        return {
            "plan_json": encode_plan(result.value),
            "usage_json": append_usage(state, result.usage, result.additional_usages),
        }

    def review(state: TDState) -> TDState:
        if not approval_required:
            return {"approval": "approved"}
        response = interrupt({"plan_json": state["plan_json"], "thread_id": state["thread_id"]})
        if response not in {"approve", "reject"}:
            raise ValidationError("Approval response must be approve or reject")
        return {"approval": "approved" if response == "approve" else "rejected"}

    def generate(state: TDState) -> TDState:
        chunks = decode_chunks(state["curriculum_json"]) + decode_chunks(state["knowledge_json"])
        result = service.generate(
            decode_request(state["request_json"]), decode_plan(state["plan_json"]), chunks
        )
        return {
            "draft_json": encode_draft(result.value),
            "usage_json": append_usage(state, result.usage, result.additional_usages),
        }

    def audit(state: TDState) -> TDState:
        chunks = decode_chunks(state["curriculum_json"]) + decode_chunks(state["knowledge_json"])
        result = service.audit(
            decode_request(state["request_json"]), decode_draft(state["draft_json"]), chunks
        )
        return {
            "issues_json": encode_issues(result.value),
            "usage_json": append_usage(state, result.usage, result.additional_usages),
        }

    def revise(state: TDState) -> TDState:
        chunks = decode_chunks(state["curriculum_json"]) + decode_chunks(state["knowledge_json"])
        result = service.revise(
            decode_draft(state["draft_json"]), decode_issues(state["issues_json"]), chunks
        )
        return {
            "draft_json": encode_draft(result.value),
            "revisions": state.get("revisions", 0) + 1,
            "usage_json": append_usage(state, result.usage, result.additional_usages),
        }

    def exhausted(state: TDState) -> TDState:
        raise AuditExhaustedError(
            f"TD audit still has errors after {max_revision_loops} revision loops"
        )

    def render(state: TDState) -> TDState:
        chunks = decode_chunks(state["curriculum_json"]) + decode_chunks(state["knowledge_json"])
        artifact = service.render(
            decode_draft(state["draft_json"]),
            source_references(chunks),
            thread_id=state["thread_id"],
        )
        return {"tex_json": encode_artifact(artifact)}

    def compile_pdf(state: TDState) -> TDState:
        tex = decode_artifact(state["tex_json"])
        pdf = service.compile(tex)
        return {"artifacts_json": encode_artifacts((tex, pdf) if pdf else (tex,))}

    def finalize(state: TDState) -> TDState:
        return {"result_json": encode_result(summarize_result(state))}

    graph.add_node("retrieve_curriculum", curriculum)
    graph.add_node("retrieve_knowledge", knowledge)
    graph.add_node("plan", plan)
    graph.add_node("review", review)
    graph.add_node("generate", generate)
    graph.add_node("audit", audit)
    graph.add_node("revise", revise)
    graph.add_node("exhausted", exhausted)
    graph.add_node("render_latex", render)
    graph.add_node("compile_pdf", compile_pdf)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "retrieve_curriculum")
    graph.add_edge("retrieve_curriculum", "retrieve_knowledge")
    graph.add_edge("retrieve_knowledge", "plan")
    graph.add_edge("plan", "review")

    def review_route(state: TDState) -> str:
        return "generate" if state["approval"] == "approved" else END

    graph.add_conditional_edges("review", review_route)
    graph.add_edge("generate", "audit")

    def audit_route(state: TDState) -> str:
        has_errors = any(
            issue.severity == Severity.ERROR for issue in decode_issues(state["issues_json"])
        )
        if not has_errors:
            return "render_latex"
        return "revise" if state.get("revisions", 0) < max_revision_loops else "exhausted"

    graph.add_conditional_edges("audit", audit_route)
    graph.add_edge("revise", "audit")
    graph.add_edge("render_latex", "compile_pdf")
    graph.add_edge("compile_pdf", "finalize")
    graph.add_edge("finalize", END)
    return graph
