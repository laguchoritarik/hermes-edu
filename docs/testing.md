# Testing strategy

## Unit tests

Offline, deterministic, fast. Focus on domain policies, parsers, routing decisions, state reducers, validation rules, and application use cases with fake ports.

## Integration tests

Test one boundary at a time: MCP client/server, provider HTTP adapter with mocks, SQLite repositories/checkpointer, RAG store, LaTeX compiler process wrapper.

## End-to-end tests

Exercise a complete vertical slice with controlled fixtures and deterministic/fake model responses by default.

## Golden tests

Store approved structural/textual artifacts or normalized snapshots for pedagogical regression. Golden updates require human review; never auto-accept a changed educational answer.

## Live tests

Tests that spend API credits or require remote services must be explicitly marked and disabled by default in CI.
