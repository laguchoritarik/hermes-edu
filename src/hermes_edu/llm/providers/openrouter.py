"""OpenRouter OpenAI-compatible chat adapter."""

from math import isfinite
from time import perf_counter
from typing import cast

import structlog
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from openai.types.chat import ChatCompletion
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from hermes_edu.application.ports.llm import (
    LLMPort,
    ModelAttemptError,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from hermes_edu.domain.errors import GenerationError

logger = structlog.get_logger(__name__)

_TRANSIENT_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


class OpenRouterChatAdapter(LLMPort):
    """Call OpenRouter's OpenAI-compatible JSON chat API with bounded retries."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        max_attempts: int = 3,
        client: OpenAI | None = None,
    ) -> None:
        if not api_key and client is None:
            raise GenerationError("OPENROUTER_API_KEY is required for OpenRouter chat")
        if not model.strip():
            raise GenerationError("OpenRouter chat model is required")
        if timeout_seconds <= 0 or max_attempts < 1:
            raise GenerationError("OpenRouter timeout and attempt limit must be positive")
        self._client = client or OpenAI(
            api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout_seconds
        )
        self._max_attempts = max_attempts
        self._model = model

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        started = perf_counter()
        try:
            response = self._call_once(request)
        except GenerationError:
            logger.info(
                "llm_call_failure",
                task=request.task,
                provider="openrouter",
                model=self._model,
                latency_ms=round((perf_counter() - started) * 1000),
            )
            raise
        latency_ms = round((perf_counter() - started) * 1000)
        model = response.model.strip() or self._model
        usage = self._usage(response, model=model, task=request.task, latency_ms=latency_ms)
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice else None
        finish_reason = choice.finish_reason if choice else "missing_choice"
        logger.info(
            "llm_call",
            task=request.task,
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=usage.cached_tokens,
            latency_ms=usage.latency_ms,
            estimated_cost_usd=usage.estimated_cost_usd,
            price_basis=usage.price_basis,
            finish_reason=finish_reason,
            has_content=bool(content),
        )
        if finish_reason == "length":
            raise ModelAttemptError(
                "Model output hit HERMES_MAX_OUTPUT_TOKENS; increase the limit and retry",
                (usage,),
                returned_outcome="invalid",
            )
        if not content or not content.strip():
            raise ModelAttemptError(
                "OpenRouter returned no JSON content", (usage,), returned_outcome="invalid"
            )
        return ModelResponse(content, usage)

    def _call_once(self, request: ModelRequest) -> ChatCompletion:
        response: ChatCompletion | None = None
        started = perf_counter()
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(self._max_attempts),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
                retry=retry_if_exception_type(_TRANSIENT_ERRORS),
                reraise=True,
            ):
                with attempt:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": request.system},
                            {"role": "user", "content": request.user},
                        ],
                        max_tokens=request.max_output_tokens,
                        response_format={"type": "json_object"},
                    )
        except _TRANSIENT_ERRORS as exc:
            raise ModelAttemptError(
                f"OpenRouter request failed after bounded retries: {type(exc).__name__}",
                (),
                timed_out=isinstance(exc, APITimeoutError),
                failed_latency_ms=round((perf_counter() - started) * 1000),
            ) from exc
        except Exception as exc:
            raise GenerationError(f"OpenRouter request failed: {type(exc).__name__}") from exc
        if response is None:
            raise GenerationError("OpenRouter request produced no response")
        return response

    def _usage(
        self, response: ChatCompletion, *, model: str, task: str, latency_ms: int
    ) -> ModelUsage:
        raw_usage = response.usage
        input_tokens = raw_usage.prompt_tokens if raw_usage else 0
        output_tokens = raw_usage.completion_tokens if raw_usage else 0
        details = raw_usage.prompt_tokens_details if raw_usage else None
        cached_tokens = details.cached_tokens if details and details.cached_tokens else 0
        estimated_cost = _estimated_cost(raw_usage.model_extra if raw_usage else None)
        return ModelUsage(
            provider="openrouter",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost,
            task=task,
            price_basis="OpenRouter response cost" if estimated_cost is not None else "",
        )


def _estimated_cost(model_extra: object) -> float | None:
    if not isinstance(model_extra, dict):
        return None
    extra = cast(dict[str, object], model_extra)
    value = extra.get("estimated_cost", extra.get("cost"))
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if isfinite(parsed) and parsed >= 0 else None
    if isinstance(value, (int, float)) and isfinite(value) and value >= 0:
        return float(value)
    return None
