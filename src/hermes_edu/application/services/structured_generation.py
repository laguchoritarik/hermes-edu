"""Bounded structured model calls shared by educational workflows."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from time import perf_counter

import structlog

from hermes_edu.application.ports.llm import (
    CandidateLLMPort,
    LLMPort,
    ModelAttemptError,
    ModelExhaustedError,
    ModelOutcome,
    ModelRequest,
    ModelUsage,
    ObservedLLMPort,
)
from hermes_edu.domain.errors import GenerationError, ValidationError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StepResult[T]:
    value: T
    usage: ModelUsage
    additional_usages: tuple[ModelUsage, ...] = ()


def validated_completion[T](
    llm: LLMPort,
    request: ModelRequest,
    parser: Callable[[str], T],
) -> StepResult[T]:
    """Validate each candidate, retaining usage from every returned response."""
    usages: list[ModelUsage] = []
    candidates = llm.candidates_for(request) if isinstance(llm, CandidateLLMPort) else (llm,)
    if not candidates:
        raise GenerationError(f"{request.task} has no configured model")
    last_failure: GenerationError | ValidationError | None = None
    for candidate in candidates:
        current = (
            replace(request, user=request.user + "\n" + _diagnostic(last_failure))
            if last_failure is not None
            else request
        )
        # Preserve the old correction attempt only when no fallback is configured.
        for retry in range(2 if len(candidates) == 1 else 1):
            started = perf_counter()
            try:
                response = candidate.complete_json(current)
            except ModelAttemptError as exc:
                usages.extend(exc.usages)
                for usage in exc.usages:
                    _observe(
                        llm,
                        ModelOutcome(
                            request.task,
                            usage.provider,
                            usage.model,
                            exc.returned_outcome,
                            usage.latency_ms,
                            usage,
                        ),
                    )
                if (exc.failed_latency_ms is not None or not exc.usages) and isinstance(
                    llm, ObservedLLMPort
                ):
                    provider, model = llm.identity_for(request, candidate)
                    llm.observe(
                        ModelOutcome(
                            request.task,
                            provider,
                            model,
                            "error",
                            exc.failed_latency_ms
                            if exc.failed_latency_ms is not None
                            else round((perf_counter() - started) * 1000),
                            timed_out=exc.timed_out,
                        )
                    )
                last_failure = exc
                break
            except GenerationError as exc:
                if isinstance(llm, ObservedLLMPort):
                    provider, model = llm.identity_for(request, candidate)
                    llm.observe(
                        ModelOutcome(
                            request.task,
                            provider,
                            model,
                            "error",
                            round((perf_counter() - started) * 1000),
                        )
                    )
                last_failure = exc
                break
            usages.extend((*response.additional_usages, response.usage))
            for usage in response.additional_usages:
                _observe(
                    llm,
                    ModelOutcome(
                        request.task,
                        usage.provider,
                        usage.model,
                        "invalid",
                        usage.latency_ms,
                        usage,
                    ),
                )
            try:
                value = parser(response.content)
            except ValidationError as exc:
                last_failure = exc
                _observe(
                    llm,
                    ModelOutcome(
                        request.task,
                        response.usage.provider,
                        response.usage.model,
                        "invalid",
                        response.usage.latency_ms,
                        response.usage,
                    ),
                )
                logger.info(
                    "llm_validation",
                    task=request.task,
                    provider=response.usage.provider,
                    model=response.usage.model,
                    outcome="invalid",
                    latency_ms=response.usage.latency_ms,
                    error=str(exc).splitlines()[0][:240],
                )
                if retry == 0 and len(candidates) == 1:
                    current = replace(
                        request,
                        user=request.user
                        + "\nPrevious JSON failed validation: "
                        + str(exc)
                        + "\nReturn corrected JSON with the exact requested fields.",
                    )
            else:
                _observe(
                    llm,
                    ModelOutcome(
                        request.task,
                        response.usage.provider,
                        response.usage.model,
                        "validated",
                        response.usage.latency_ms,
                        response.usage,
                    ),
                )
                logger.info(
                    "llm_validation",
                    task=request.task,
                    provider=response.usage.provider,
                    model=response.usage.model,
                    outcome="validated",
                    latency_ms=response.usage.latency_ms,
                )
                return StepResult(value, usages[-1], tuple(usages[:-1]))
    if len(candidates) == 1 and isinstance(last_failure, ValidationError):
        raise ModelExhaustedError(
            f"{request.task} JSON failed validation twice: {last_failure}", tuple(usages)
        ) from last_failure
    raise ModelExhaustedError(
        f"{request.task} exhausted configured models: {last_failure}", tuple(usages)
    ) from last_failure


def _diagnostic(failure: GenerationError | ValidationError) -> str:
    if isinstance(failure, ValidationError):
        reason = str(failure).splitlines()[0][:160]
        return f"Previous JSON failed validation: {reason}. Return corrected JSON."
    return "Previous model failed to produce usable JSON. Return complete valid JSON."


def _observe(llm: object, outcome: ModelOutcome) -> None:
    if isinstance(llm, ObservedLLMPort):
        llm.observe(outcome)
