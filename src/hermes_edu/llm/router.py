"""Task-based routing between configured provider-neutral model ports."""

from hermes_edu.application.ports.llm import (
    LLMPort,
    ModelOutcome,
    ModelOutcomeStorePort,
    ModelRequest,
    ModelResponse,
)


class TaskRoutedLLM(LLMPort):
    """Route audit and revision calls explicitly to their configured models."""

    def __init__(
        self,
        *,
        primary: LLMPort,
        audit: LLMPort,
        revision: LLMPort,
        alternatives: dict[str, tuple[LLMPort, ...]] | None = None,
        labels: dict[str, tuple[tuple[str, str], ...]] | None = None,
        outcomes: ModelOutcomeStorePort | None = None,
    ) -> None:
        self._primary = primary
        self._audit = audit
        self._revision = revision
        self._alternatives = alternatives or {}
        self._labels = labels or {}
        self._outcomes = outcomes

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        return self.candidates_for(request)[0].complete_json(request)

    def candidates_for(self, request: ModelRequest) -> tuple[LLMPort, ...]:
        """Keep configured preference fixed; validation decides when to advance."""
        if request.task == "audit":
            selected = self._audit
        elif request.task == "revise":
            selected = self._revision
        else:
            selected = self._primary
        candidates = (selected, *self._alternatives.get(request.task, ()))
        if request.candidate_offset < 0:
            raise ValueError("candidate_offset must be nonnegative")
        offset = request.candidate_offset % len(candidates)
        return candidates[offset:] + candidates[:offset]

    def identity_for(self, request: ModelRequest, candidate: LLMPort) -> tuple[str, str]:
        """Identify failed calls that returned no provider usage."""
        full_request = ModelRequest(
            request.system, request.user, request.max_output_tokens, request.task
        )
        for index, port in enumerate(self.candidates_for(full_request)):
            if port is candidate:
                labels = self._labels.get(request.task, ())
                if index < len(labels):
                    return labels[index]
        return ("unknown", "unknown")

    def observe(self, outcome: ModelOutcome) -> None:
        if self._outcomes is not None:
            self._outcomes.record(outcome)
