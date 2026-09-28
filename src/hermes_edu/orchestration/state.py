"""Checkpoint-safe, typed TD workflow state and boundary codecs."""

# LangGraph supplies keys progressively; each node reads only keys guaranteed by its incoming edge.
# pyright: reportTypedDictNotRequiredAccess=false

import json
from dataclasses import asdict
from typing import TypedDict

from pydantic import TypeAdapter

from hermes_edu.application.ports.llm import ModelUsage
from hermes_edu.domain.models.audit import AuditIssue
from hermes_edu.domain.models.document import Artifact, TDDraft, TDPlan, TDResult
from hermes_edu.domain.models.request import TDRequest
from hermes_edu.domain.models.source import RetrievedChunk, SourceReference


class TDState(TypedDict, total=False):
    request_json: str
    thread_id: str
    route: str
    curriculum_json: str
    knowledge_json: str
    plan_json: str
    approval: str
    draft_json: str
    issues_json: str
    revisions: int
    usage_json: str
    tex_json: str
    artifacts_json: str
    result_json: str


def encode_request(value: TDRequest) -> str:
    return json.dumps(asdict(value))


def decode_request(value: str) -> TDRequest:
    return TypeAdapter(TDRequest).validate_json(value)


def encode_chunks(values: tuple[RetrievedChunk, ...]) -> str:
    return json.dumps([asdict(value) for value in values])


def decode_chunks(value: str) -> tuple[RetrievedChunk, ...]:
    return TypeAdapter(tuple[RetrievedChunk, ...]).validate_json(value)


def encode_plan(value: TDPlan) -> str:
    return json.dumps(asdict(value))


def decode_plan(value: str) -> TDPlan:
    return TypeAdapter(TDPlan).validate_json(value)


def encode_draft(value: TDDraft) -> str:
    return json.dumps(asdict(value))


def decode_draft(value: str) -> TDDraft:
    return TypeAdapter(TDDraft).validate_json(value)


def encode_issues(values: tuple[AuditIssue, ...]) -> str:
    return json.dumps([asdict(value) for value in values])


def decode_issues(value: str) -> tuple[AuditIssue, ...]:
    return TypeAdapter(tuple[AuditIssue, ...]).validate_json(value)


def encode_artifact(value: Artifact) -> str:
    return json.dumps(asdict(value))


def decode_artifact(value: str) -> Artifact:
    return TypeAdapter(Artifact).validate_json(value)


def encode_artifacts(values: tuple[Artifact, ...]) -> str:
    return json.dumps([asdict(value) for value in values])


def decode_artifacts(value: str) -> tuple[Artifact, ...]:
    return TypeAdapter(tuple[Artifact, ...]).validate_json(value)


def append_usage(state: TDState, usage: ModelUsage, additional: tuple[ModelUsage, ...] = ()) -> str:
    records = decode_usage(state.get("usage_json", "[]"))
    return json.dumps([asdict(record) for record in (*records, *additional, usage)])


def decode_usage(value: str) -> tuple[ModelUsage, ...]:
    return TypeAdapter(tuple[ModelUsage, ...]).validate_json(value)


def summarize_result(state: TDState) -> TDResult:
    chunks = decode_chunks(state["curriculum_json"]) + decode_chunks(
        state.get("knowledge_json", "[]")
    )
    sources = tuple({chunk.source.source_id: chunk.source for chunk in chunks}.values())
    usages = decode_usage(state.get("usage_json", "[]"))
    costs = [usage.estimated_cost_usd for usage in usages]
    return TDResult(
        thread_id=state["thread_id"],
        draft=decode_draft(state["draft_json"]),
        sources=sources,
        artifacts=decode_artifacts(state["artifacts_json"]),
        revisions=state.get("revisions", 0),
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        cached_tokens=sum(usage.cached_tokens for usage in usages),
        estimated_cost_usd=sum(cost for cost in costs if cost is not None)
        if all(cost is not None for cost in costs)
        else None,
        usage=usages,
    )


def encode_result(value: TDResult) -> str:
    return json.dumps(asdict(value))


def decode_result(value: str) -> TDResult:
    return TypeAdapter(TDResult).validate_json(value)


def source_references(chunks: tuple[RetrievedChunk, ...]) -> tuple[SourceReference, ...]:
    return tuple({chunk.source.source_id: chunk.source for chunk in chunks}.values())
