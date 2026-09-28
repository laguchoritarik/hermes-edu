"""Complete offline TD graph including persistent approval and bounded repair."""

# Third-party LangGraph/Pytest overloads retain unknown generic parameters in strict mode.
# pyright: reportUnknownMemberType=false

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from hermes_edu.application.ports.llm import ModelRequest, ModelResponse, ModelUsage
from hermes_edu.application.use_cases.create_td import CreateTD
from hermes_edu.domain.errors import AuditExhaustedError, GenerationError
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.document import Artifact
from hermes_edu.domain.models.request import TDRequest
from hermes_edu.domain.models.source import RetrievedChunk, SourceReference
from hermes_edu.orchestration.graphs.main import build_main_graph
from hermes_edu.orchestration.state import TDState, decode_result, encode_request


class ScriptedLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.tasks: list[str] = []

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        self.tasks.append(request.task)
        return ModelResponse(
            self.responses.pop(0),
            ModelUsage("fake", "fixed", 10, 5, 0, 1, 0.001),
        )


class StaticRetriever:
    def retrieve(
        self, query: str, context: LearningContext, *, kind: str, top_k: int
    ) -> tuple[RetrievedChunk, ...]:
        return (
            RetrievedChunk(
                "sample:0",
                "Eigenvalues and eigenspaces",
                SourceReference("sample", "Sample", "local", "CC0"),
                1.0,
            ),
        )


class FakeDocuments:
    def render(self, draft: object, sources: object, *, thread_id: str) -> Artifact:
        return Artifact("tex", f"/tmp/{thread_id}.tex", "a" * 64, 100)

    def compile(self, tex_artifact: Artifact) -> Artifact:
        return Artifact("pdf", tex_artifact.path.replace(".tex", ".pdf"), "b" * 64, 200)


PLAN = '{"title":"Reduction TD","exercises":[{"title":"Eigenvalues","objective":"Find eigenvalues","difficulty":1}]}'
DRAFT = '{"title":"Reduction TD","exercises":[{"title":"Eigenvalues","statement":"Find eigenvalues of a diagonal matrix","solution":"Read the diagonal entries","source_ids":["sample"]}]}'
REVISED = '{"title":"Eigenvalues","statement":"Find eigenvalues of diag(1,2)","solution":"They are 1 and 2","source_ids":["sample"]}'
PASS = '{"issues":[]}'
FAIL = '{"issues":[{"severity":"error","category":"math","exercise_index":1,"explanation":"Fix the values"}]}'


def _graph(tmp_path: Path, llm: ScriptedLLM, approval: bool, revisions: int):
    service = CreateTD(
        llm=llm,
        retriever=StaticRetriever(),
        documents=FakeDocuments(),
        top_k=2,
        context_token_budget=500,
        max_output_tokens=500,
    )
    saver = SqliteSaver.from_conn_string(str(tmp_path / "checkpoints.db"))
    return build_main_graph(
        service, approval_required=approval, max_revision_loops=revisions
    ), saver


def _input(thread_id: str) -> TDState:
    request = TDRequest("Reduction", LearningContext("sample", "MP"), exercise_count=1)
    return {"request_json": encode_request(request), "thread_id": thread_id}


def test_success_and_usage(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, DRAFT, PASS])
    builder, saver = _graph(tmp_path, llm, False, 2)
    with saver as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        state = graph.invoke(_input("success"), config={"configurable": {"thread_id": "success"}})
    result = decode_result(state["result_json"])
    assert [artifact.kind for artifact in result.artifacts] == ["tex", "pdf"]
    assert result.input_tokens == 30
    assert result.estimated_cost_usd == pytest.approx(0.003)
    assert result.sources[0].source_id == "sample"


def test_revision_is_targeted_and_bounded(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, DRAFT, FAIL, REVISED, PASS])
    builder, saver = _graph(tmp_path, llm, False, 1)
    with saver as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        state = graph.invoke(_input("revision"), config={"configurable": {"thread_id": "revision"}})
    assert decode_result(state["result_json"]).revisions == 1
    assert llm.tasks == ["plan", "generate", "audit", "revise", "audit"]


def test_invalid_plan_gets_one_accounted_correction(tmp_path: Path) -> None:
    invalid = '{"title":"Wrong","exercises":[]}'
    llm = ScriptedLLM([invalid, PLAN, DRAFT, PASS])
    builder, saver = _graph(tmp_path, llm, False, 1)
    with saver as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        state = graph.invoke(
            _input("plan-retry"), config={"configurable": {"thread_id": "plan-retry"}}
        )
    result = decode_result(state["result_json"])
    assert llm.tasks == ["plan", "plan", "generate", "audit"]
    assert len(result.usage) == 4
    assert result.input_tokens == 40


def test_invalid_plan_correction_is_bounded(tmp_path: Path) -> None:
    llm = ScriptedLLM(['{"title":"Wrong","exercises":[]}' for _ in range(2)])
    builder, saver = _graph(tmp_path, llm, False, 1)
    with saver as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        with pytest.raises(GenerationError, match="twice"):
            graph.invoke(_input("plan-fail"), config={"configurable": {"thread_id": "plan-fail"}})
    assert llm.tasks == ["plan", "plan"]


def test_audit_exhaustion(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, DRAFT, FAIL])
    builder, saver = _graph(tmp_path, llm, False, 0)
    with saver as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        with pytest.raises(AuditExhaustedError):
            graph.invoke(_input("exhaust"), config={"configurable": {"thread_id": "exhaust"}})


def test_approval_resumes_without_repeating_plan(tmp_path: Path) -> None:
    llm = ScriptedLLM([PLAN, DRAFT, PASS])
    builder, saver = _graph(tmp_path, llm, True, 1)
    config: RunnableConfig = {"configurable": {"thread_id": "approval"}}
    with saver as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        paused = graph.invoke(_input("approval"), config=config)
        assert "__interrupt__" in paused
        assert llm.tasks == ["plan"]
    # A new SQLite saver represents a later process resuming the same thread.
    with SqliteSaver.from_conn_string(str(tmp_path / "checkpoints.db")) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        state = graph.invoke(Command(resume="approve"), config=config)
    assert decode_result(state["result_json"]).draft.title == "Reduction TD"
    assert llm.tasks == ["plan", "generate", "audit"]
