"""Dated provider price-table selection and model isolation."""

from datetime import UTC, datetime

from hermes_edu.llm.models import deepseek_flash_rates


def test_flash_price_snapshot_selects_peak_and_off_peak() -> None:
    peak = deepseek_flash_rates("deepseek-flash", datetime(2026, 9, 28, 2, tzinfo=UTC))
    off_peak = deepseek_flash_rates("deepseek-flash", datetime(2026, 9, 27, 2, tzinfo=UTC))
    assert peak is not None and off_peak is not None
    assert peak.input_usd_per_million == 0.3
    assert off_peak.input_usd_per_million == 0.15
    assert off_peak.cached_input_usd_per_million == 0.003
    assert deepseek_flash_rates("custom-model", datetime(2026, 9, 27, tzinfo=UTC)) is None
