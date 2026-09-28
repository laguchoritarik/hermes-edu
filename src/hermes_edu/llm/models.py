"""Dated DeepSeek Flash price estimates, isolated from core contracts."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TokenRates:
    input_usd_per_million: float
    cached_input_usd_per_million: float
    output_usd_per_million: float
    basis: str


def deepseek_flash_rates(model: str, at_utc: datetime) -> TokenRates | None:
    """Return the published 2026-09-27 rates for the named Flash model only."""
    if model != "deepseek-flash":
        return None
    hour = at_utc.hour
    peak = at_utc.weekday() < 5 and (1 <= hour < 4 or 6 <= hour < 10)
    if peak:
        return TokenRates(0.3, 0.006, 1.2, "DeepSeek Flash 2026-09-27 peak")
    return TokenRates(0.15, 0.003, 0.6, "DeepSeek Flash 2026-09-27 off-peak")
