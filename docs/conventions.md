# Coding and architecture conventions

- Prefer explicit typed models over loosely shaped dictionaries at stable boundaries.
- Keep functions small and side effects visible.
- Use async at I/O boundaries; do not make pure domain functions async.
- Raise domain/application-specific errors instead of parsing provider error strings in core code.
- Never branch on provider name in use cases; use a provider registry/router port.
- Keep retries bounded and only for transient failures.
- Use structured logs; avoid `print()` in library code.
- Store stable raw data in state; format prompts close to model calls.
- Add an ADR for new foundational frameworks, persistence technologies, or cross-layer dependencies.
- Prefer a thin vertical slice over creating unused abstractions.
