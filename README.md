# Hermes Edu

> **Status: architecture scaffold / pre-alpha.** The repository intentionally contains structure, contracts, documentation, tests, and configuration before production implementation.

Hermes Edu is an open-source educational agent architecture designed to create and maintain high-quality **courses, exercise sheets/TDs, homework/DMs, tests/DSs, corrections, explanations, and LaTeX/PDF documents**. The initial domain is mathematics, but the architecture is intentionally provider- and curriculum-agnostic.

The project is designed around four ideas:

1. **Clean Architecture / ports & adapters** so the educational core does not depend on DeepSeek, OpenRouter, SQLite, MCP, LangGraph, or a web framework.
2. **LangGraph for orchestration** of stateful, long-running workflows: routing, revision loops, checkpoints, human approval, and subgraphs.
3. **MCP Python SDK v2 as a standardized boundary** for tools, resources, and prompts — not as the business core.
4. **RAG as an independent knowledge subsystem** so curricula, courses, exercise banks, and references can be indexed and retrieved without coupling retrieval to the LLM provider.

---

## 1. What Hermes Edu should eventually do

A user should be able to ask naturally:

```text
Create an MP-level TD on reduction, 8 progressive exercises,
with a detailed correction, following the official curriculum,
and generate the final PDF.
```

The system should then execute a controlled workflow:

```text
request
  ↓
understand intent and educational context
  ↓
select workflow (course / TD / DM / DS / correction / explanation)
  ↓
retrieve official curriculum + relevant knowledge
  ↓
plan document
  ↓
human approval when configured
  ↓
generate draft
  ↓
audit mathematics + curriculum + pedagogy
  ↓
revise until valid or retry limit reached
  ↓
render LaTeX
  ↓
compile + inspect PDF
  ↓
return artifacts
```

The LLM is never the only authority. Deterministic checks, retrieval provenance, tool validation, and human approval remain part of the workflow.

---

## 2. Architecture in one diagram

```mermaid
flowchart TD
    UI[CLI / API / MCP Host] --> BOOT[Composition root / bootstrap]
    BOOT --> GRAPH[LangGraph orchestration]
    GRAPH --> APP[Application use cases]
    APP --> DOMAIN[Domain models & policies]

    GRAPH --> PORTS[Application ports]
    PORTS --> LLM[LLM adapters]
    PORTS --> KNOW[Knowledge / RAG adapters]
    PORTS --> MCP[MCP gateway]
    PORTS --> DOC[LaTeX / PDF adapters]
    PORTS --> PERSIST[Persistence adapters]

    LLM --> DS[DeepSeek]
    LLM --> DI[DeepInfra]
    LLM --> OR[OpenRouter]
    KNOW --> SQLITE[(SQLite / vector index)]
    PERSIST --> CKPT[(LangGraph checkpoints)]
```

### Dependency direction

The dependency rule is more important than the folder names:

```text
interfaces / orchestration / adapters
              ↓
          application
              ↓
            domain
```

`domain/` must remain framework-independent. Infrastructure implements **ports** defined by the application layer.

---

## 3. Why LangGraph?

Hermes is not just a single prompt. A reliable educational document workflow needs:

- shared state;
- deterministic and LLM nodes;
- conditional routing;
- generation → audit → correction loops;
- bounded retries;
- checkpoints and thread IDs;
- pause/resume;
- human-in-the-loop approval;
- subgraphs for course / TD / DM / DS;
- optional parallel work later.

LangGraph is therefore the **workflow engine**, not the domain model.

---

## 4. Why MCP?

MCP provides a standard way to expose or consume:

- **Tools**: actions such as compile LaTeX, inspect a document, query a search service;
- **Resources**: curricula, course documents, templates, references;
- **Prompts**: reusable workflows/instructions.

Hermes uses MCP as an adapter. The core must still be usable directly as a Python library without an MCP server.

```text
hermes_edu core
    ├── Python/CLI/API usage
    └── MCP exposure / MCP consumption
```

---

## 5. Why RAG is separate from MCP

RAG answers: **which small pieces of knowledge are relevant?**

MCP answers: **how are tools/resources/prompts exposed in a standard protocol?**

The knowledge pipeline remains independent:

```text
PDF/Markdown/LaTeX
      ↓
ingestion
      ↓
normalization
      ↓
chunking
      ↓
embeddings
      ↓
store/index
      ↓
retriever
      ↓
Top-k chunks + provenance
```

The graph may then insert those chunks into LLM context or expose them through MCP.

---

## 6. Repository layout

```text
hermes-edu/
├── src/hermes_edu/
│   ├── domain/          # Pure educational concepts and rules
│   ├── application/     # Use cases + abstract ports
│   ├── orchestration/   # LangGraph states, nodes, routes, graphs
│   ├── llm/             # Provider adapters and provider routing
│   ├── mcp/             # MCP client/server boundary
│   ├── knowledge/       # Ingestion, chunks, embeddings, retrieval, stores
│   ├── documents/       # LaTeX/PDF/template deterministic pipeline
│   ├── persistence/     # Checkpoints and repositories
│   ├── config/          # Settings and paths
│   ├── observability/   # Logs/tracing/metrics
│   ├── interfaces/      # CLI and optional HTTP API
│   └── bootstrap.py     # Composition root / dependency wiring
├── data/                # Local source/index data; content is ignored by Git
├── workspace/           # Generated outputs; content is ignored by Git
├── tests/               # unit / integration / e2e / golden
├── docs/                # architecture + specification + ADRs
├── .github/             # CI, issue forms, dependabot
└── pyproject.toml        # package + dependencies + tools
```

See `FILES_MANIFEST.md` for the role of every scaffold file.

---

## 7. Layer responsibilities

### `domain/`

Pure educational language: document types, curriculum context, exercises, audit issues, sources, policies, domain errors. **No SDK/framework imports.**

### `application/`

Defines use cases such as `create_td`, `create_course`, `audit_document`, and the **ports** those use cases require: LLM, retriever, embeddings, MCP, compiler, repositories, checkpoints.

### `orchestration/`

Owns LangGraph only: state schemas, graph context, nodes, routers, subgraphs, retry/revision flow, human approval. Nodes should call application services/ports rather than contain large provider implementations.

### `llm/`

Provider-independent model interface plus DeepSeek, DeepInfra, and OpenRouter adapters. Provider switching must not leak into domain/application code.

### `mcp/`

MCP v2 client/server integration. It exposes Hermes capabilities or consumes external capabilities. Filesystem/tool execution must be allowlisted and validated.

### `knowledge/`

Document ingestion, normalization, chunking, embeddings, vector/hybrid retrieval, reranking, and stores. Retrieval results must retain provenance.

### `documents/`

Deterministic rendering and output pipeline: templates, LaTeX writing/validation/compilation, PDF inspection. Generated code is treated as untrusted until validated.

### `persistence/`

LangGraph checkpoints and application repositories. SQLite is the first local backend; production can later add PostgreSQL without changing core use cases.

### `interfaces/`

Thin delivery mechanisms only: CLI and optional HTTP API. No business logic.

### `bootstrap.py`

The **composition root**. This is the one place allowed to know concrete adapters and wire them to abstract ports.

---

## 8. Non-negotiable architecture rules

1. No `agent.py` containing the whole system.
2. No direct DeepSeek/OpenRouter/DeepInfra calls outside provider adapters.
3. No direct MCP plumbing in the domain layer.
4. No direct SQLite access from domain/use-case code.
5. No LaTeX shell execution from an LLM-generated string without validation and sandbox restrictions.
6. No hidden provider-specific fields in domain models.
7. State stores raw/structured data; prompts are built near the model call, not stored as the canonical state.
8. LLM outputs that control execution must be parsed/validated as structured data.
9. Revision loops have explicit limits.
10. External data keeps source/provenance metadata.
11. Human approval is required for configured high-impact actions.
12. Framework replacement must be possible through adapter changes rather than domain rewrites.

---

## 9. Dependency strategy

Core dependencies are intentionally small:

- `langgraph` — orchestration;
- `langgraph-checkpoint-sqlite` — local durable checkpoints;
- `mcp` v2 — MCP protocol client/server;
- `openai` — OpenAI-compatible provider adapter base for current providers;
- `pydantic` / `pydantic-settings` — typed models and configuration;
- `httpx` — HTTP infrastructure;
- `tenacity` — bounded retry policies;
- `structlog` — structured logs;
- `platformdirs` — portable local paths.

Optional extras:

- `cli`: Typer + Rich;
- `rag`: NumPy + PyMuPDF + sqlite-vec;
- `latex`: Jinja2;
- `api`: FastAPI + Uvicorn;
- `langchain`: intentionally optional; Hermes does **not** require LangChain.

See `docs/dependencies.md`.

---

## 10. Development setup

### Requirements

- Python **3.12+**
- `uv`
- Git
- XeLaTeX/TeX Live only when the LaTeX pipeline is implemented/tested

### Install

```bash
cp .env.example .env
uv sync --all-extras --all-groups
uv run pre-commit install
```

`uv` will create `.venv` and `uv.lock`. The lockfile should be committed after the first successful dependency resolution.

### Quality commands

```bash
make lint
make typecheck
make test
make audit
make check
```

---

## 11. Environment and secrets

`.env.example` documents all expected variables. Real `.env` files are ignored.

Important defaults:

```text
LANGGRAPH_STRICT_MSGPACK=true
HERMES_HUMAN_APPROVAL_REQUIRED=true
HERMES_MAX_REVISION_LOOPS=3
```

API keys are adapter configuration, never domain data.

---

## 12. Checkpoints and persistence

Local development uses SQLite-backed LangGraph checkpoints. A workflow is associated with a `thread_id`; checkpoints allow pause/resume and human-in-the-loop flows.

Checkpoint storage is **not** the same thing as the RAG/vector store or long-term educational repository. They may both use SQLite locally, but they have different schemas and responsibilities.

---

## 13. Testing strategy

The project distinguishes:

- **Unit tests**: pure domain/application logic, no network;
- **Integration tests**: MCP client/server, repositories, provider adapters with mocked HTTP, retrieval backends;
- **E2E tests**: request → workflow → document artifact;
- **Golden tests**: approved educational outputs/structures used for regression checks.

Network-dependent tests must be explicitly marked and disabled by default in CI.

---

## 14. Security model

Hermes processes untrusted text, model output, external documents, and potentially executable document pipelines. Security is therefore architectural:

- allowlist filesystem roots;
- never trust model-selected tool names without validation;
- validate structured outputs;
- harden checkpoint deserialization;
- do not enable unrestricted LaTeX shell escape;
- isolate generated artifacts in `workspace/`;
- do not commit private student/course data;
- audit dependencies in CI;
- require human approval for configured actions.

See `docs/security.md`.

---

## 15. Planned graph structure

```mermaid
flowchart TD
  START --> ANALYZE[Analyze request]
  ANALYZE --> ROUTE{Workflow?}
  ROUTE --> COURSE[Course subgraph]
  ROUTE --> TD[TD subgraph]
  ROUTE --> DM[DM subgraph]
  ROUTE --> DS[DS subgraph]
  ROUTE --> CORR[Correction subgraph]

  TD --> CURR[Retrieve curriculum]
  CURR --> KNOW[Retrieve knowledge]
  KNOW --> PLAN[Plan]
  PLAN --> APPROVE{Human approval?}
  APPROVE -->|revise| PLAN
  APPROVE -->|approved| GEN[Generate]
  GEN --> AUDIT[Audit]
  AUDIT --> VALID{Valid?}
  VALID -->|no| REVISE[Revise]
  REVISE --> AUDIT
  VALID -->|yes| LATEX[Render LaTeX]
  LATEX --> PDF[Compile & inspect PDF]
  PDF --> END
```

The exact node boundaries are allowed to evolve through ADRs.

---

## 16. Initial product scope

The architecture is broad, but implementation should proceed through thin vertical slices.

The first useful slice should support **one mathematics workflow** end-to-end rather than partially implementing every directory. Suggested first slice:

```text
Math → one curriculum/track → TD generation
→ curriculum retrieval → RAG → plan → approval
→ generation → audit → revision → LaTeX/PDF
```

Only after this slice is reliable should the same abstractions be generalized to courses, DMs, DSs, multiple curricula, and additional providers.

---

## 17. Documentation for developers

Start here:

1. `docs/project-specification.md` — initial cahier des charges;
2. `docs/architecture.md` — boundaries and dependency rules;
3. `FILES_MANIFEST.md` — every scaffold file and its purpose;
4. `docs/roadmap.md` — implementation order;
5. `docs/adr/` — decisions and rationale.

---

## 18. Current status

This archive is deliberately an **architecture-first scaffold**. Python modules contain placeholders/docstrings rather than production implementations. Configuration, CI, documentation, dependency declaration, and repository boundaries are established so implementation can begin without creating architectural debt.

## License

Apache-2.0 is used as the default open-source license in this scaffold. Change this before first public release if the maintainers prefer another license.
