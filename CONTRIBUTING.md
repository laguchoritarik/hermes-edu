# Contributing

Thank you for contributing to Hermes Edu.

## Local setup

```bash
git clone <repository-url>
cd hermes-edu
cp .env.example .env
uv sync --all-extras --all-groups
uv run pre-commit install
```

## Before a pull request

```bash
make check
uv run pip-audit
```

## Architecture rule

Follow the dependency direction documented in `docs/architecture.md`. In particular:

- `domain/` must not import LangGraph, MCP, provider SDKs, SQLite, or FastAPI.
- provider-specific code belongs under `llm/providers/`.
- orchestration belongs under `orchestration/`.
- MCP is an adapter/boundary, not the core of Hermes.
- RAG/indexing code belongs under `knowledge/`.
- deterministic document/file work belongs under `documents/`.

For non-trivial design changes, add or update an ADR.
