# AGENTS.md — Hermes Edu

## Mission

Hermes Edu is an open-source educational agent for creating, auditing, revising, and producing
courses, TDs, DMs, DSs, corrections, explanations, and LaTeX/PDF artifacts.

This repository is architecture-first. Preserve the architecture while implementing thin,
working vertical slices.

## Read before changing code

For any non-trivial task, read the relevant parts of:

1. `README.md`
2. `docs/project-specification.md`
3. `docs/architecture.md`
4. `docs/roadmap.md`
5. `FILES_MANIFEST.md`
6. relevant files under `docs/adr/`
7. the closest nested `AGENTS.md`

Treat those documents as the source of truth. If an implementation requires a durable
architectural change, create/update an ADR and the architecture documentation in the same patch.

## Dependency rule

Dependencies point inward:

`interfaces / orchestration / adapters -> application -> domain`

Never invert this rule.

- `domain/` is pure Python business/domain logic and must not import LangGraph, MCP, provider SDKs,
  SQLite, HTTP clients, FastAPI/Typer, Jinja2, or infrastructure adapters.
- `application/` owns use cases and ports. It depends on `domain/`, not concrete adapters.
- `orchestration/` owns LangGraph only and coordinates application services/ports.
- provider, MCP, RAG, persistence, document, CLI/API code are adapters at the outside.
- `bootstrap.py` is the composition root allowed to wire concrete implementations to ports.

## Non-negotiable architecture constraints

- No monolithic `agent.py`, `utils.py`, `helpers.py`, or god object.
- No direct DeepSeek/DeepInfra/OpenRouter API calls outside provider adapters.
- No direct MCP client/server plumbing in domain or use cases.
- No direct SQLite access in domain/use-case code.
- No provider-specific fields in domain models.
- No framework object/client/session in checkpointed LangGraph state.
- LangGraph state stores structured/raw data, not giant preformatted prompts.
- LLM outputs that affect control flow must be structured and validated.
- All loops/retries are bounded.
- External/retrieved information retains provenance.
- Generated LaTeX is untrusted until validated and compiled under restricted settings.
- Never use unrestricted shell escape for LaTeX.
- Never commit secrets, private data, `.env`, generated local databases, or user documents.
- Do not add LangChain unless a concrete need is demonstrated and documented in an ADR.
- Do not introduce multi-agent architecture until a single-agent graph is measurably insufficient.

## Clean-code rules

- Python 3.12+ and strict typing.
- Prefer explicit domain names over generic names such as `data`, `item`, `manager`, `processor`.
- Keep functions focused on one responsibility.
- Keep side effects at system boundaries.
- Prefer immutable/value-style models for domain data where practical.
- Use `Protocol`/ports for substitutable external capabilities.
- Validate untrusted boundary input with Pydantic or equivalent typed parsing.
- Avoid `Any`; if unavoidable at an external boundary, localize it and explain why.
- Avoid broad `except Exception` unless translating/logging at a boundary; never silently swallow errors.
- Raise domain/application-specific exceptions rather than leaking raw provider exceptions inward.
- Public APIs and non-obvious behavior require concise docstrings.
- Comments explain *why*, invariants, tradeoffs, or safety constraints — not obvious syntax.
- Avoid duplicated logic. Extract a shared abstraction only after the common responsibility is clear.
- Prefer composition over inheritance.
- Keep imports acyclic.
- No hidden global mutable state.
- Use `structlog`; do not add ad-hoc `print()` in library code.
- Never log secrets, full private documents, or API keys.

## LLM and token/cost rules

- Minimize context before changing model size.
- Retrieve/select before loading large resources.
- Never send full document libraries to an LLM when top-k retrieval is sufficient.
- Do not send every MCP tool/resource/prompt to the model; expose only relevant candidates.
- Use deterministic Python/tools for work that does not require language reasoning.
- Use the cheapest adequate model for routing/classification; reserve stronger models for difficult generation/audit.
- Track input/output/cached tokens, provider, model, latency, and estimated cost for every model call.
- Keep provider pricing/configuration out of domain logic.
- Context builders must have explicit token budgets and graceful truncation/summarization behavior.
- Cache safe, deterministic/repeatable results where beneficial.
- Corrections should be targeted; do not regenerate an entire document when a bounded section can be repaired.

## LangGraph rules

- Nodes are thin orchestration units; large provider/RAG/compiler implementations live outside nodes.
- State is typed and contains serializable data only.
- Use reducers intentionally for accumulative fields.
- Human approval uses `interrupt()`/resume where configured.
- Use durable checkpoints for long-running workflows.
- Revision/audit loops must enforce `HERMES_MAX_REVISION_LOOPS`.
- Deterministic decisions remain deterministic Python routing; use an LLM only when semantic interpretation is needed.
- Subgraphs are preferred for course/TD/DM/DS/correction workflows once behavior diverges.

## MCP rules

- MCP is an adapter/boundary, not the business core.
- Validate tool names and arguments before execution.
- Restrict filesystem access to configured allowlisted roots.
- Resources expose data; tools perform actions; prompts expose reusable workflows.
- Stable core capabilities should remain callable directly as Python APIs without MCP.

## RAG rules

- Preserve source/provenance and chunk identifiers.
- Keep ingestion, chunking, embedding, storage, retrieval, and reranking separate.
- Embeddings are generated once and reused when source/version has not changed.
- Retrieval behavior must be testable without live provider calls.
- Do not make the vector store or embedding provider part of domain models.

## Testing and quality

Every behavior change must include appropriate tests.

- Unit: no network, deterministic domain/application behavior.
- Integration: adapters with mocks/fakes or local resources.
- E2E: one complete user workflow.
- Golden: approved educational structures/artifacts where useful.
- Network-dependent tests are explicitly marked and disabled by default.

Before finishing, run:

```bash
make lint
make typecheck
make test
make build
```

Run `make audit` when network/package-index access is available.
If any required check fails, fix it or report the exact external blocker. Do not claim success with failing checks.

## Work strategy

1. Inspect before editing.
2. Write/update an execution plan for large tasks.
3. Implement one thin vertical slice at a time.
4. Keep the repository runnable after each coherent phase.
5. Prefer small cohesive commits/patches.
6. Do not fill placeholder files merely to make them non-empty.
7. Remove dead code rather than keeping speculative abstractions.
8. Update docs and examples when behavior or architecture changes.
9. Do not change an architecture boundary silently.
10. At completion, summarize changed files, tests run, remaining risks, and next recommended slice.
