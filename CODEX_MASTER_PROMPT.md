# Codex Master Prompt — Implement Hermes Edu v0.1

You are the principal engineer responsible for turning this repository from an architecture scaffold
into a clean, maintainable, tested, open-source Hermes Edu v0.1.

Work from the repository root.

## First: understand the repository

Before editing implementation code:

1. Read `AGENTS.md` and every nested `AGENTS.md` relevant to files you will touch.
2. Read:
   - `README.md`
   - `docs/project-specification.md`
   - `docs/architecture.md`
   - `docs/roadmap.md`
   - `FILES_MANIFEST.md`
   - all existing `docs/adr/*.md`
   - `pyproject.toml`
   - `.env.example`
   - `Makefile`
3. Inspect the current source tree and tests.
4. Do not assume placeholder/docstring files are implementations.
5. Do not redesign the architecture casually. If a durable change is required, write an ADR first.

## Objective

Implement the first complete vertical slice of Hermes Edu:

**Mathematics -> one configurable curriculum/track -> TD generation -> curriculum/RAG retrieval ->
plan -> optional human approval -> generation -> audit -> bounded revision -> LaTeX rendering ->
controlled XeLaTeX compilation -> final artifacts + provenance + usage/cost metadata.**

The result must be usable through a CLI and testable without live network access.

This is a real v0.1 implementation, not a demo script and not a collection of stubs.

Do not try to fill every placeholder file in the repository. Implement only the modules needed for the
vertical slice and its architectural contracts. Leave future modules as documented placeholders until
they are needed.

## Execution-plan requirement

Create and maintain:

`docs/exec-plans/active/0001-v0.1-implementation.md`

The plan must contain:

- current repository assessment;
- architecture constraints;
- phased implementation checklist;
- exact modules expected to change;
- acceptance criteria for each phase;
- test strategy;
- external dependencies/blockers;
- risks and mitigations;
- decisions requiring ADRs;
- progress log.

Update this file as work proceeds. When the v0.1 acceptance criteria are satisfied, move it to
`docs/exec-plans/completed/`.

Do not stop after writing the plan. Execute it.

## Implementation order

### Phase 1 — baseline and contracts

- Resolve/install dependencies using the existing `pyproject.toml`.
- Generate `uv.lock` if dependency resolution is available.
- Preserve Python 3.12+ and strict Pyright.
- Implement the minimal domain models required by the TD slice.
- Implement application ports before concrete adapters.
- Implement configuration/settings and portable local paths.
- Add/adjust tests before or alongside behavior.
- Keep the package importable and `make check` green after the phase.

Expected domain concepts include, when justified by the existing specification:
- document type;
- learning/curriculum context;
- generation request and constraints;
- source/provenance reference;
- retrieved chunk/reference;
- TD plan/section/exercise representation;
- generated draft;
- audit issue/severity/category;
- artifact metadata/result;
- token/usage/cost record;
- explicit domain/application errors.

Do not leak provider, transport, SQL, LangGraph, or MCP details into these models.

### Phase 2 — LLM provider boundary and optimization telemetry

Implement the application LLM contract and at least the DeepSeek adapter using the repository's
OpenAI-compatible client dependency.

Requirements:
- provider-neutral request/response types;
- structured-output support for control-flow decisions;
- bounded retry policy for retryable failures;
- dependency-injected/mockable HTTP/client layer;
- normalized token usage;
- latency and estimated cost telemetry;
- no secrets in logs;
- explicit context/token budget support;
- no unbounded history, resources, or tools in a model call.

Keep DeepInfra/OpenRouter as clean adapters if they can be implemented without compromising the first
slice; otherwise preserve their contracts/placeholders and document the next step.

Do not introduce LangChain unless an ADR demonstrates a concrete benefit.

### Phase 3 — local knowledge/RAG vertical slice

Implement:
- normalized document model;
- Markdown/LaTeX/PDF ingestion needed by the first slice;
- deterministic chunking;
- embedding port;
- DeepInfra embedding adapter when configured;
- deterministic fake embedding adapter for tests;
- local SQLite/vector store using the declared project dependencies;
- index/update logic that does not re-embed unchanged chunks;
- top-k retrieval with provenance;
- retrieval tests that run offline.

Add one small public/example curriculum fixture suitable for tests/demo. Do not add copyrighted/private
course corpora.

The runtime must retrieve relevant chunks rather than sending entire source documents to the model.

### Phase 4 — TD application use case

Implement a coherent application service/use case for creating a TD.

It must:
1. validate the request/context;
2. retrieve curriculum/context;
3. produce a structured plan;
4. generate a draft;
5. audit the draft;
6. revise only when required;
7. enforce a configured revision limit;
8. preserve provenance;
9. return structured artifacts/metadata.

The use case depends on ports, never concrete provider/database/compiler adapters.

### Phase 5 — LangGraph orchestration

Implement the TD subgraph and the minimal main router graph.

Required flow:

`START -> analyze request -> route -> retrieve curriculum -> retrieve knowledge -> plan ->
(optional interrupt for human approval) -> generate -> audit -> [revise -> audit]* ->
render LaTeX -> compile/inspect -> finalize -> END`

Requirements:
- typed serializable state;
- reducers only for fields that genuinely accumulate;
- live services/clients in run context, never checkpoint state;
- deterministic routers when structured state already contains the answer;
- bounded revision loops;
- SQLite checkpointer;
- stable `thread_id`;
- human approval controlled by configuration;
- tests covering success, revision loop, max-retry failure, and approval/resume.

### Phase 6 — LaTeX/PDF pipeline

Implement one versioned TD template and controlled compilation.

Requirements:
- Jinja2 only in the document adapter layer;
- generated LaTeX treated as untrusted;
- workspace path allowlisting;
- explicit subprocess argument list;
- XeLaTeX timeout;
- no unrestricted shell escape;
- capture compiler logs/exit code;
- typed compile result;
- actionable compiler error extraction;
- no LLM call for deterministic compile/file operations;
- unit/integration tests that can skip cleanly when XeLaTeX is unavailable.

### Phase 7 — CLI

Implement a thin Typer CLI for the v0.1 slice.

At minimum provide:
- environment/doctor command;
- ingest/index command for local knowledge;
- TD generation command;
- optional non-interactive approval flag for tests/automation.

The CLI must call the composition root/application/orchestration; it must not contain business logic.

### Phase 8 — MCP v2 integration

Once the Python/core v0.1 path is stable, expose stable capabilities through MCP v2.

At minimum:
- controlled curriculum/template resources;
- knowledge-search and LaTeX-validation/compile tools where appropriate;
- reusable TD prompt/workflow template if useful.

MCP must delegate to core/application services rather than duplicate logic.
Validate tool arguments and paths. Keep stdio stdout protocol-safe.

### Phase 9 — quality, documentation, packaging

- Update README with an actual v0.1 quickstart and architecture flow.
- Update `FILES_MANIFEST.md` for new/changed roles.
- Add ADRs for durable new decisions.
- Add examples that use public/synthetic data.
- Ensure `.env.example` documents every setting actually read by code.
- Add/maintain CI checks.
- Make error messages actionable.
- Build the package successfully.

## Cost/token engineering is a first-class acceptance criterion

Implement the project so that long workflows can be materially cheaper than a naive agent.

At minimum:
- retrieval before context injection;
- top-k bounded context;
- explicit token budgets;
- relevant-tool selection rather than sending all tools to every model call;
- small/cheap model path for classification/routing where configured;
- stronger model path only for difficult generation/audit where configured;
- usage/cost telemetry for every LLM call;
- safe caching where deterministic/repeatable;
- checkpoint/resume so successful expensive phases are not needlessly repeated;
- targeted revision rather than whole-document regeneration where feasible.

Document the optimization strategy and expose enough telemetry to compare runs.

## Clean-code acceptance rules

Obey all `AGENTS.md` files. Additionally:

- strict typing must pass;
- no `Any` spread through core code;
- no circular imports;
- no hidden global mutable state;
- no generic god services;
- no direct concrete-adapter imports from domain/application use cases;
- no duplicated provider logic;
- no giant prompts embedded across multiple files;
- no giant LangGraph nodes;
- no silent exception handling;
- no network dependency in unit tests;
- no fake "success" paths that skip real validation;
- no hardcoded personal paths;
- no committed secrets/private data;
- no speculative abstraction without a real use in the vertical slice.

Prefer readable code over clever code. Public interfaces and non-obvious invariants get concise
docstrings. Comments explain why, not what.

## Validation loop

After every coherent phase:
1. format/lint;
2. strict typecheck;
3. unit/integration tests relevant to the phase;
4. run existing tests;
5. inspect architecture dependency direction;
6. update the execution plan.

Before declaring completion, run:

```bash
make lint
make typecheck
make test
make build
```

Run `make audit` if package-index/network access is available.

Also run the CLI happy path with synthetic/public fixture data. If XeLaTeX is installed, compile the
sample TD PDF. If unavailable, prove the compiler adapter behavior with tests and report the external
dependency clearly.

## Git/repository discipline

- Do not rewrite or discard existing architecture docs without justification.
- Do not delete user work.
- Keep changes cohesive.
- Do not commit `.env`, keys, local DBs, generated private artifacts, or caches.
- If Git is initialized and commits are expected by the environment, use descriptive commits per
  coherent phase and leave the worktree clean.
- Never claim a check passed unless you ran it.

## How to handle uncertainty

- Inspect current package APIs/source/docs instead of guessing.
- Prefer the repository's declared versions and architecture.
- If network access is unavailable, continue with offline-testable implementation and record the exact
  blocker.
- If an API key is absent, use fakes for tests and make the real adapter configurable; do not hardcode
  fake production responses.
- Do not ask me to approve ordinary implementation decisions already covered by the specification.
  Make the best architecture-consistent choice and document material decisions in ADRs.

## Definition of done for v0.1

Do not report v0.1 complete until all are true:

- repository installs from `pyproject.toml`;
- strict typecheck/lint/tests pass;
- one TD workflow runs end-to-end with synthetic/public local knowledge;
- structured request and output models are validated;
- RAG retrieves bounded, provenance-aware context;
- optional human approval can interrupt/resume the LangGraph thread;
- audit/revision loop is bounded and tested;
- a `.tex` artifact is produced;
- PDF compiles when XeLaTeX is available, with controlled failure otherwise;
- usage/token/cost metadata is recorded;
- checkpoints persist locally;
- CLI happy path works;
- stable core capabilities are exposed through MCP v2 without duplicating core logic;
- README/setup/examples/docs match actual behavior;
- no secrets/private data are committed;
- architecture dependency rules remain intact;
- `make lint`, `make typecheck`, `make test`, and `make build` pass.

When done, give me:
1. a concise implementation summary;
2. architecture decisions/ADRs added;
3. exact validation commands and results;
4. remaining external prerequisites;
5. known limitations;
6. recommended v0.2 backlog ordered by impact.
