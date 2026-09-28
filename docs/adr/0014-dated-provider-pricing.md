# 0014 — Dated provider-side cost estimates

Status: **Accepted**
Date: 2026-09-27

## Context

A null cost field for every default-model call makes run comparison harder even when token usage is known. Provider prices vary by model, cache status and time period and can change after release.

## Decision

Keep a dated `deepseek-flash` peak/off-peak price snapshot in the provider layer, based on the [published DeepSeek pricing table](https://api-docs.deepseek.com/quick_start/pricing/) accessed on 2026-09-27. Estimate uncached input, cached input and output separately. Label each usage record with its price basis. Explicit environment rates override the snapshot. Unknown models or missing usage report unknown cost.

## Consequences

The number is an estimate, not a bill. Maintainers must review the snapshot when pricing changes; users can override rates immediately without a code release. No prices enter domain rules or workflow routing.

## Alternatives considered

Fetching live prices for every request would add network latency and a new failure path. Reporting only null would not meet v0.1 cost observability goals.
