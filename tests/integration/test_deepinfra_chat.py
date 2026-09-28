"""DeepInfra chat calls remain OpenAI-compatible and task-routable offline."""

# The OpenAI SDK's bundled httpx2 type differs from compatible httpx at runtime.
# pyright: reportArgumentType=false
# pyright: reportPrivateUsage=false

import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError as PydanticValidationError

from hermes_edu.application.ports.llm import (
    LLMPort,
    ModelAttemptError,
    ModelOutcome,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from hermes_edu.bootstrap import build_llm
from hermes_edu.config.settings import Settings
from hermes_edu.domain.errors import ValidationError
from hermes_edu.llm.providers.deepinfra import DeepInfraChatAdapter
from hermes_edu.llm.providers.openrouter import OpenRouterChatAdapter
from hermes_edu.llm.router import TaskRoutedLLM


def _client(respond: httpx.MockTransport) -> OpenAI:
    return OpenAI(
        api_key="test-only",
        base_url="https://example.test/v1/openai",
        http_client=httpx.Client(transport=respond),
        max_retries=0,
    )


def test_deepinfra_chat_sends_flagship_json_request_and_accounts_response_cost() -> None:
    captured: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chat-1",
                "object": "chat.completion",
                "created": 0,
                "model": "Qwen/Qwen3.5-397B-A17B",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"valid":true}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "prompt_tokens_details": {"cached_tokens": 30},
                    "estimated_cost": 0.0042,
                },
            },
        )

    adapter = DeepInfraChatAdapter(
        api_key="",
        base_url="https://example.test/v1/openai",
        client=_client(httpx.MockTransport(respond)),
    )
    result = adapter.complete_json(ModelRequest("system", "user", 256, "audit"))

    assert captured["model"] == "Qwen/Qwen3-Next-80B-A3B-Instruct"
    assert captured["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in captured
    assert result.content == '{"valid":true}'
    assert result.usage.provider == "deepinfra"
    assert result.usage.model == "Qwen/Qwen3.5-397B-A17B"
    assert result.usage.task == "audit"
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20
    assert result.usage.cached_tokens == 30
    assert result.usage.estimated_cost_usd == 0.0042
    assert result.usage.price_basis == "DeepInfra response estimated_cost"


def test_deepinfra_chat_uses_configured_rates_when_cost_is_absent() -> None:
    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-2",
                "object": "chat.completion",
                "created": 0,
                "model": "metadata-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "{}"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "prompt_tokens_details": {"cached_tokens": 30},
                },
            },
        )

    adapter = DeepInfraChatAdapter(
        api_key="",
        base_url="https://example.test/v1/openai",
        input_cost_per_million_usd=2,
        cached_input_cost_per_million_usd=0.5,
        output_cost_per_million_usd=4,
        client=_client(httpx.MockTransport(respond)),
    )

    result = adapter.complete_json(ModelRequest("system", "user", 32, "revise"))

    assert result.usage.model == "metadata-model"
    assert result.usage.estimated_cost_usd == 0.000235
    assert result.usage.price_basis == "configured rates"


def test_deepinfra_chat_rejects_length_finished_content() -> None:
    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chat-3",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "length",
                        "message": {"role": "assistant", "content": "{}"},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 32, "total_tokens": 33},
            },
        )

    adapter = DeepInfraChatAdapter(
        api_key="",
        base_url="https://example.test/v1/openai",
        client=_client(httpx.MockTransport(respond)),
    )

    with pytest.raises(ModelAttemptError, match="MAX_OUTPUT") as failure:
        adapter.complete_json(ModelRequest("system", "user", 32, "audit"))
    assert failure.value.usages[0].output_tokens == 32


def test_openrouter_chat_sends_json_request_and_records_usage() -> None:
    captured: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "or-1",
                "object": "chat.completion",
                "created": 0,
                "model": "anthropic/claude-sonnet-4.5",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"issues":[]}'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 10,
                    "total_tokens": 60,
                    "cost": "0.0012",
                },
            },
        )

    adapter = OpenRouterChatAdapter(
        api_key="",
        base_url="https://example.test/v1",
        model="anthropic/claude-sonnet-4.5",
        client=_client(httpx.MockTransport(respond)),
    )

    result = adapter.complete_json(ModelRequest("system", "user", 128, "audit"))

    assert captured["model"] == "anthropic/claude-sonnet-4.5"
    assert captured["response_format"] == {"type": "json_object"}
    assert result.content == '{"issues":[]}'
    assert result.usage.provider == "openrouter"
    assert result.usage.model == "anthropic/claude-sonnet-4.5"
    assert result.usage.estimated_cost_usd == 0.0012


@dataclass
class _RecordingLLM(LLMPort):
    name: str
    calls: list[str] = field(default_factory=lambda: list[str]())

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request.task)
        return ModelResponse("{}", ModelUsage(self.name, self.name, 1, 1, 0, 1, 0.0))


@pytest.mark.parametrize(
    ("task", "expected"),
    (
        ("plan", "primary"),
        ("generate", "primary"),
        ("verify", "primary"),
        ("audit", "audit"),
        ("revise", "revision"),
    ),
)
def test_task_router_sends_audit_and_revision_to_explicit_ports(task: str, expected: str) -> None:
    primary = _RecordingLLM("primary")
    audit = _RecordingLLM("audit")
    revision = _RecordingLLM("revision")
    router = TaskRoutedLLM(primary=primary, audit=audit, revision=revision)

    response = router.complete_json(ModelRequest("system", "user", 32, task))

    assert response.usage.provider == expected
    assert primary.calls == ([task] if expected == "primary" else [])
    assert audit.calls == ([task] if expected == "audit" else [])
    assert revision.calls == ([task] if expected == "revision" else [])


def test_bootstrap_configures_ordered_review_and_generation_fallbacks() -> None:
    settings = Settings(
        deepseek_api_key="test-only",
        deepinfra_api_key="test-only",
        openrouter_api_key="test-only",
        openrouter_model="anthropic/claude-sonnet-4.5",
        hermes_audit_provider="deepinfra",
        hermes_audit_model="Qwen/Qwen3-Next-80B-A3B-Instruct",
        hermes_audit_fallback_models="openrouter:anthropic/claude-sonnet-4.5,Qwen/Qwen3.5-35B-A3B,deepseek",
        hermes_generation_fallback_models="openrouter:anthropic/claude-sonnet-4.5,Qwen/Qwen3.5-35B-A3B",
    )

    router = build_llm(settings)

    assert isinstance(router, TaskRoutedLLM)
    audit = router.candidates_for(ModelRequest("s", "u", 128, "audit"))
    generation = router.candidates_for(ModelRequest("s", "u", 128, "generate"))
    assert len(audit) == 4
    assert isinstance(audit[0], DeepInfraChatAdapter)
    assert audit[0]._model == "Qwen/Qwen3-Next-80B-A3B-Instruct"
    assert audit[0]._max_attempts == 1
    assert isinstance(audit[1], OpenRouterChatAdapter)
    assert audit[1]._model == "anthropic/claude-sonnet-4.5"
    assert audit[1]._max_attempts == 1
    assert isinstance(audit[2], DeepInfraChatAdapter)
    assert audit[2]._model == "Qwen/Qwen3.5-35B-A3B"
    assert audit[3] is generation[0]
    assert isinstance(generation[1], OpenRouterChatAdapter)
    assert isinstance(generation[2], DeepInfraChatAdapter)
    verify = router.candidates_for(ModelRequest("s", "u", 128, "verify"))
    assert verify[0] is generation[0]
    assert isinstance(verify[1], OpenRouterChatAdapter)


def test_bootstrap_can_use_openrouter_as_task_primary() -> None:
    settings = Settings(
        deepseek_api_key="test-only",
        openrouter_api_key="test-only",
        openrouter_model="anthropic/claude-sonnet-4.5",
        hermes_audit_provider="openrouter",
        hermes_audit_model="",
        hermes_audit_fallback_models="deepseek",
    )

    router = build_llm(settings)

    assert isinstance(router, TaskRoutedLLM)
    audit = router.candidates_for(ModelRequest("s", "u", 128, "audit"))
    assert isinstance(audit[0], OpenRouterChatAdapter)
    assert audit[0]._model == "anthropic/claude-sonnet-4.5"


def test_fallback_configuration_rejects_unbounded_or_repeated_models() -> None:
    with pytest.raises(PydanticValidationError, match="1-4 distinct"):
        Settings(hermes_generation_fallback_models="a,b,c,d,e")
    with pytest.raises(PydanticValidationError, match="1-4 distinct"):
        Settings(hermes_generation_fallback_models="a,a")
    with pytest.raises(ValidationError, match="repeats its preferred model"):
        build_llm(
            Settings(
                deepseek_api_key="test-only",
                hermes_generation_fallback_models="deepseek",
            )
        )


def test_metrics_path_uses_runtime_root(tmp_path: Path) -> None:
    settings = Settings(deepseek_api_key="test-only")
    router = build_llm(settings, root=tmp_path)
    assert isinstance(router, TaskRoutedLLM)
    router.observe(ModelOutcome("plan", "deepseek", "flash", "validated", 5))
    assert (tmp_path / settings.hermes_llm_metrics_db_path).exists()
