# 0013 — Checkpointed TD plan approval and bounded repair

Status: **Accepted**
Date: 2026-09-27

## Context

An educator must be able to inspect a plan before expensive generation. A failed exercise should be repaired without regenerating a full TD, and retries must be bounded.

## Decision

The main LangGraph graph validates and routes a structured request to a TD subgraph. The subgraph retrieves, plans, optionally interrupts for approval, generates, audits, repairs one error-bearing exercise per pass, renders, compiles and finalizes. SQLite checkpoints use stable thread IDs and strict msgpack. State contains only JSON-serializable domain values and usage records; live adapters stay in the composition root. `HERMES_MAX_REVISION_LOOPS` bounds repair. Explicit `--yes` skips approval for automation.

## Consequences

A rejected plan ends the thread without artifacts. Exhausted audits raise a typed failure and preserve the last checkpoint for diagnosis. Resuming requires the same local configuration, including the compilation choice. Additional workflow types will require separate subgraphs and routing decisions.

## Alternatives considered

A synchronous monolithic use case would hide approval/resume and retry behavior. Re-running the complete workflow on resume would duplicate provider cost.
