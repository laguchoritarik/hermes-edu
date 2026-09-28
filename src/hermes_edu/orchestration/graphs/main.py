"""Minimal main router for the supported v0.1 TD workflow."""

# LangGraph's dynamic node overloads and progressive state keys are wider than its static stubs.
# pyright: reportTypedDictNotRequiredAccess=false, reportUnknownMemberType=false

from langgraph.graph import END, START, StateGraph

from hermes_edu.application.use_cases.create_td import CreateTD
from hermes_edu.orchestration.graphs.td import build_td_graph
from hermes_edu.orchestration.state import TDState, decode_request


def build_main_graph(
    service: CreateTD, *, approval_required: bool, max_revision_loops: int
) -> StateGraph[TDState]:
    graph = StateGraph(TDState)

    def analyze(state: TDState) -> TDState:
        decode_request(state["request_json"])
        return {}

    def select_workflow(state: TDState) -> TDState:
        return {"route": "td"}

    def route(state: TDState) -> str:
        return state["route"]

    graph.add_node("analyze_request", analyze)
    graph.add_node("select_workflow", select_workflow)
    graph.add_node(
        "td",
        build_td_graph(
            service, approval_required=approval_required, max_revision_loops=max_revision_loops
        ).compile(),
    )
    graph.add_edge(START, "analyze_request")
    graph.add_edge("analyze_request", "select_workflow")
    graph.add_conditional_edges("select_workflow", route, {"td": "td"})
    graph.add_edge("td", END)
    return graph
