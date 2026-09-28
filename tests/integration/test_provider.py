"""DeepSeek adapter maps an OpenAI-compatible response without network access."""

# OpenAI's bundled httpx2 client type differs from the compatible httpx transport at runtime.
# pyright: reportArgumentType=false

import json

import httpx
import pytest
from openai import OpenAI

from hermes_edu.application.ports.llm import ModelAttemptError, ModelRequest
from hermes_edu.llm.providers.deepseek import DeepSeekAdapter


def test_deepseek_usage_and_json_contract() -> None:
    captured: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chat-1",
                "object": "chat.completion",
                "created": 0,
                "model": "cheap",
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

    client = OpenAI(
        api_key="test-only",
        base_url="https://example.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_retries=0,
    )
    adapter = DeepSeekAdapter(
        api_key="",
        base_url="https://example.test/v1",
        model="cheap",
        generation_model="strong",
        input_cost_per_million_usd=1,
        cached_input_cost_per_million_usd=0.1,
        output_cost_per_million_usd=2,
        client=client,
    )
    response = adapter.complete_json(ModelRequest("system", "user", 128, "plan"))
    assert captured["model"] == "cheap"
    assert captured["reasoning_effort"] == "none"
    assert captured["response_format"] == {"type": "json_object"}
    assert response.content == "{}"
    assert response.usage.cached_tokens == 30
    assert response.usage.estimated_cost_usd == 0.000113


def test_empty_json_is_retried_and_accounted() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "id": f"chat-{calls}",
                "object": "chat.completion",
                "created": 0,
                "model": "cheap",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "" if calls == 1 else "{}"},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    client = OpenAI(
        api_key="test-only",
        base_url="https://example.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_retries=0,
    )
    adapter = DeepSeekAdapter(
        api_key="", base_url="https://example.test/v1", model="deepseek-flash", client=client
    )
    result = adapter.complete_json(ModelRequest("system", "user", 128, "plan"))
    assert calls == 2
    assert len(result.additional_usages) == 1
    assert result.additional_usages[0].output_tokens == 5
    assert result.usage.estimated_cost_usd is not None
    assert result.usage.price_basis.startswith("DeepSeek Flash 2026-09-27")


def test_deepseek_with_fallback_does_not_retry_empty_or_transport_error() -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "id": "chat-empty",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-flash",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": ""},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            },
        )

    adapter = DeepSeekAdapter(
        api_key="",
        base_url="https://example.test/v1",
        model="deepseek-flash",
        fallback_tasks=frozenset({"verify"}),
        client=OpenAI(
            api_key="test-only",
            base_url="https://example.test/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
            max_retries=0,
        ),
    )
    with pytest.raises(ModelAttemptError) as failure:
        adapter.complete_json(ModelRequest("system", "user", 128, "verify"))
    assert calls == 1
    assert failure.value.returned_outcome == "invalid"
    assert len(failure.value.usages) == 1


def test_deepseek_with_fallback_uses_one_transport_attempt() -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    adapter = DeepSeekAdapter(
        api_key="",
        base_url="https://example.test/v1",
        model="deepseek-flash",
        fallback_tasks=frozenset({"verify"}),
        client=OpenAI(
            api_key="test-only",
            base_url="https://example.test/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
            max_retries=0,
        ),
    )
    with pytest.raises(ModelAttemptError):
        adapter.complete_json(ModelRequest("system", "user", 128, "verify"))
    assert calls == 1
