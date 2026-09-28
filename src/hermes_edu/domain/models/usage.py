"""Provider-neutral accounting for one language model call."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelUsage:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms: int
    estimated_cost_usd: float | None
    task: str = ""
    price_basis: str = ""
