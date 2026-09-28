"""Offline validation of explicit model fallback and usage accounting."""

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from hermes_edu.application.ports.llm import (
    LLMPort,
    ModelAttemptError,
    ModelExhaustedError,
    ModelOutcome,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from hermes_edu.application.services.structured_generation import validated_completion
from hermes_edu.domain.errors import GenerationError, ValidationError
from hermes_edu.llm.router import TaskRoutedLLM
from hermes_edu.persistence.model_outcomes import SQLiteModelOutcomeStore


@dataclass
class ScriptedPort(LLMPort):
    provider: str
    responses: list[str | GenerationError]
    calls: list[ModelRequest] = field(default_factory=lambda: list[ModelRequest]())

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        next_response = self.responses.pop(0)
        if isinstance(next_response, GenerationError):
            raise next_response
        return ModelResponse(
            next_response,
            ModelUsage(self.provider, self.provider, 10, 5, 0, 10, 0.01, task=request.task),
        )


def _parse(content: str) -> str:
    if content != '{"valid":true}':
        raise ValidationError("Invalid JSON or schema")
    return content


@pytest.mark.parametrize("failure", ["{}", GenerationError("timeout")])
def test_validation_or_provider_failure_switches_to_next_candidate(
    failure: str | GenerationError,
) -> None:
    first = ScriptedPort("first", [failure])
    second = ScriptedPort("second", ['{"valid":true}'])
    router = TaskRoutedLLM(
        primary=first,
        audit=first,
        revision=first,
        alternatives={"audit": (second,)},
    )

    result = validated_completion(router, ModelRequest("rules", "payload", 100, "audit"), _parse)

    assert result.usage.provider == "second"
    assert len(first.calls) == len(second.calls) == 1
    assert [usage.provider for usage in result.additional_usages] == (
        ["first"] if isinstance(failure, str) else []
    )
    assert "Previous" in second.calls[0].user
    assert "{}" not in second.calls[0].user


def test_no_fallback_keeps_one_schema_correction() -> None:
    primary = ScriptedPort("primary", ["{}", '{"valid":true}'])

    result = validated_completion(primary, ModelRequest("rules", "payload", 100, "plan"), _parse)

    assert len(primary.calls) == 2
    assert "Previous JSON failed validation" in primary.calls[1].user
    assert len(result.additional_usages) == 1


def test_exhausted_candidates_raise_generation_error() -> None:
    first = ScriptedPort("first", ["{}"])
    second = ScriptedPort("second", ["{}"])
    router = TaskRoutedLLM(
        primary=first, audit=first, revision=first, alternatives={"generate": (second,)}
    )

    with pytest.raises(ModelExhaustedError, match="exhausted configured models") as failure:
        validated_completion(router, ModelRequest("rules", "payload", 100, "generate"), _parse)
    assert len(first.calls) == len(second.calls) == 1
    assert [usage.provider for usage in failure.value.usages] == ["first", "second"]


def test_explicit_offset_starts_later_repair_on_alternative() -> None:
    first = ScriptedPort("first", ['{"valid":true}'])
    second = ScriptedPort("second", ['{"valid":true}'])
    router = TaskRoutedLLM(
        primary=first, audit=first, revision=first, alternatives={"revise": (second,)}
    )

    result = validated_completion(
        router, ModelRequest("rules", "payload", 100, "revise", candidate_offset=1), _parse
    )

    assert result.usage.provider == "second"
    assert not first.calls


@pytest.mark.parametrize("offset", [1, 3, 5])
def test_offset_rotates_full_fallback_chain_after_repeated_revisions(offset: int) -> None:
    first = ScriptedPort("first", ['{"valid":true}'])
    second = ScriptedPort("second", [GenerationError("unavailable")])
    router = TaskRoutedLLM(
        primary=first, audit=first, revision=first, alternatives={"revise": (second,)}
    )

    result = validated_completion(
        router, ModelRequest("rules", "payload", 100, "revise", candidate_offset=offset), _parse
    )

    assert result.usage.provider == "first"
    assert len(first.calls) == len(second.calls) == 1


def test_offset_equal_to_candidate_count_keeps_all_candidates() -> None:
    first = ScriptedPort("first", [GenerationError("unavailable")])
    second = ScriptedPort("second", [GenerationError("unavailable")])
    third = ScriptedPort("third", ['{"valid":true}'])
    router = TaskRoutedLLM(
        primary=first,
        audit=first,
        revision=first,
        alternatives={"revise": (second, third)},
    )

    result = validated_completion(
        router, ModelRequest("rules", "payload", 100, "revise", candidate_offset=3), _parse
    )

    assert result.usage.provider == "third"
    assert all(len(port.calls) == 1 for port in (first, second, third))


def test_sqlite_outcome_report_keeps_only_aggregate_metadata(tmp_path: Path) -> None:
    store = SQLiteModelOutcomeStore(tmp_path / "metrics.db")
    assert store.summary() == ()
    usage = ModelUsage("deepinfra", "qwen", 12, 4, 0, 25, 0.01, task="verify")
    store.record(ModelOutcome("verify", "deepinfra", "qwen", "validated", 25, usage))
    store.record(ModelOutcome("verify", "deepinfra", "qwen", "invalid", 35, usage))
    store.record(ModelOutcome("verify", "deepinfra", "qwen", "error", 40, timed_out=True))
    summary = store.summary()
    assert len(summary) == 1
    assert (summary[0].validated, summary[0].invalid, summary[0].errors) == (1, 1, 1)
    assert summary[0].timeouts == 1
    assert summary[0].mean_latency_ms == 100 / 3
    assert summary[0].total_input_tokens == 24
    assert summary[0].estimated_cost_usd is None


def test_validation_outcomes_are_recorded_for_each_candidate(tmp_path: Path) -> None:
    store = SQLiteModelOutcomeStore(tmp_path / "metrics.db")
    first = ScriptedPort("first", ["{}"])
    second = ScriptedPort("second", ['{"valid":true}'])
    router = TaskRoutedLLM(
        primary=first,
        audit=first,
        revision=first,
        alternatives={"verify": (second,)},
        outcomes=store,
    )

    validated_completion(router, ModelRequest("rules", "payload", 100, "verify"), _parse)

    summary = {row.provider: row for row in store.summary()}
    assert summary["first"].invalid == 1
    assert summary["second"].validated == 1


def test_timeout_after_empty_response_has_separate_outcomes(tmp_path: Path) -> None:
    store = SQLiteModelOutcomeStore(tmp_path / "metrics.db")
    previous = ModelUsage("deepseek", "flash", 10, 1, 0, 4, 0.001, task="verify")
    first = ScriptedPort(
        "deepseek",
        [
            ModelAttemptError(
                "timeout",
                (previous,),
                returned_outcome="invalid",
                timed_out=True,
                failed_latency_ms=60000,
            )
        ],
    )
    second = ScriptedPort("deepinfra", ['{"valid":true}'])
    router = TaskRoutedLLM(
        primary=first,
        audit=first,
        revision=first,
        alternatives={"verify": (second,)},
        labels={"verify": (("deepseek", "flash"), ("deepinfra", "qwen"))},
        outcomes=store,
    )

    validated_completion(router, ModelRequest("rules", "payload", 100, "verify"), _parse)

    summary = {row.provider: row for row in store.summary()}
    assert (summary["deepseek"].invalid, summary["deepseek"].errors) == (1, 1)
    assert summary["deepseek"].timeouts == 1
    assert summary["deepseek"].mean_latency_ms == 30002
