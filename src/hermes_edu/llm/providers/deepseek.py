"""DeepSeek's OpenAI-compatible chat adapter."""

from datetime import UTC, datetime
from time import perf_counter

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
from hermes_edu.llm.models import deepseek_flash_rates

logger = structlog.get_logger(__name__)


class DeepSeekAdapter(LLMPort):
    """JSON-only model calls with bounded retries and per-call usage."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        generation_model: str = "",
        audit_model: str = "",
        plan_reasoning_effort: str = "none",
        generation_reasoning_effort: str = "low",
        audit_reasoning_effort: str = "low",
        input_cost_per_million_usd: float | None = None,
        cached_input_cost_per_million_usd: float | None = None,
        output_cost_per_million_usd: float | None = None,
        timeout_seconds: float = 60.0,
        max_attempts: int = 3,
        fallback_tasks: frozenset[str] = frozenset(),
        client: OpenAI | None = None,
    ) -> None:
        if not api_key and client is None:
            raise GenerationError("DEEPSEEK_API_KEY is required for live generation")
        if timeout_seconds <= 0 or max_attempts < 1:
            raise GenerationError("DeepSeek timeout and attempt limit must be positive")
        self._client = client or OpenAI(
            api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout_seconds
        )
        self._max_attempts = max_attempts
        self._fallback_tasks = fallback_tasks
        self._model = model
        self._generation_model = generation_model or model
        self._audit_model = audit_model or model
        self._plan_effort = plan_reasoning_effort
        self._generation_effort = generation_reasoning_effort
        self._audit_effort = audit_reasoning_effort
        self._input_price = input_cost_per_million_usd
        self._cached_input_price = cached_input_cost_per_million_usd
        self._output_price = output_cost_per_million_usd

    def _call_once(self, request: ModelRequest, *, model: str, effort: str) -> ChatCompletion:
        response: ChatCompletion | None = None
        started = perf_counter()
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(
                    1 if request.task in self._fallback_tasks else self._max_attempts
                ),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
                retry=retry_if_exception_type(
                    (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)
                ),
                reraise=True,
            ):
                with attempt:
                    response = self._client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": request.system},
                            {"role": "user", "content": request.user},
                        ],
                        max_tokens=request.max_output_tokens,
                        response_format={"type": "json_object"},
                        extra_body={"reasoning_effort": effort},
                    )
        except (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError) as exc:
            raise ModelAttemptError(
                f"Model request failed after bounded retries: {type(exc).__name__}",
                (),
                timed_out=isinstance(exc, APITimeoutError),
                failed_latency_ms=round((perf_counter() - started) * 1000),
            ) from exc
        except Exception as exc:
            raise GenerationError(f"Model request failed: {type(exc).__name__}") from exc
        if response is None:
            raise GenerationError("Model request produced no response")
        return response

    def _usage(
        self, response: ChatCompletion, *, model: str, task: str, latency_ms: int
    ) -> ModelUsage:
        raw_usage = response.usage
        input_tokens = raw_usage.prompt_tokens if raw_usage else 0
        output_tokens = raw_usage.completion_tokens if raw_usage else 0
        details = raw_usage.prompt_tokens_details if raw_usage else None
        cached_tokens = details.cached_tokens if details and details.cached_tokens else 0
        estimated_cost: float | None = None
        price_basis = ""
        input_price = 0.0
        cached_price = 0.0
        output_price = 0.0
        if (
            raw_usage is not None
            and self._input_price is not None
            and self._output_price is not None
        ):
            input_price = self._input_price
            output_price = self._output_price
            cached_price = (
                self._cached_input_price if self._cached_input_price is not None else input_price
            )
            price_basis = "configured rates"
        elif raw_usage is not None and all(
            price is None
            for price in (self._input_price, self._cached_input_price, self._output_price)
        ):
            published = deepseek_flash_rates(model, datetime.now(UTC))
            if published is not None:
                input_price = published.input_usd_per_million
                cached_price = published.cached_input_usd_per_million
                output_price = published.output_usd_per_million
                price_basis = published.basis
        if price_basis:
            estimated_cost = (
                max(input_tokens - cached_tokens, 0) * input_price
                + cached_tokens * cached_price
                + output_tokens * output_price
            ) / 1_000_000
        return ModelUsage(
            provider="deepseek",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost,
            task=task,
            price_basis=price_basis,
        )

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        model, effort = self._model, self._plan_effort
        if request.task in {"generate", "revise"}:
            model, effort = self._generation_model, self._generation_effort
        elif request.task in {"audit", "verify"}:
            model, effort = self._audit_model, self._audit_effort
        attempts: list[ModelUsage] = []
        empty_attempts = 1 if request.task in self._fallback_tasks else 2
        for _ in range(empty_attempts):
            start = perf_counter()
            try:
                response = self._call_once(request, model=model, effort=effort)
            except GenerationError as exc:
                if attempts:
                    raise ModelAttemptError(
                        str(exc),
                        tuple(attempts),
                        timed_out=isinstance(exc, ModelAttemptError) and exc.timed_out,
                        returned_outcome="invalid",
                        failed_latency_ms=(
                            exc.failed_latency_ms
                            if isinstance(exc, ModelAttemptError)
                            and exc.failed_latency_ms is not None
                            else round((perf_counter() - start) * 1000)
                        ),
                    ) from exc
                raise
            usage = self._usage(
                response,
                model=model,
                task=request.task,
                latency_ms=round((perf_counter() - start) * 1000),
            )
            attempts.append(usage)
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
                    tuple(attempts),
                    returned_outcome="invalid",
                )
            if content:
                return ModelResponse(content, usage, tuple(attempts[:-1]))
        raise ModelAttemptError(
            "Model returned empty JSON content after bounded attempts",
            tuple(attempts),
            returned_outcome="invalid",
        )
