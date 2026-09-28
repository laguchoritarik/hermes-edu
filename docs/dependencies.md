# Dependency policy

## Core

| Package | Role |
|---|---|
| langgraph | Stateful workflow orchestration |
| langgraph-checkpoint-sqlite | Local durable graph checkpoints |
| mcp | MCP Python SDK v2 |
| openai | Current OpenAI-compatible client used by provider adapters |
| pydantic | Validation and structured models |
| pydantic-settings | Environment/settings loading |
| httpx | HTTP infrastructure |
| tenacity | Bounded retries around transient external failures |
| structlog | Structured logging |
| platformdirs | Portable application data/config locations |

## Optional extras

### `cli`
Typer and Rich for a developer/user CLI.

### `rag`
NumPy, PyMuPDF, sqlite-vec for the existing local TD retrieval path, and hnswlib for the persistent personal-reference cosine ANN index. The native hnswlib index avoids an additional Qdrant service for this local use case.

### `latex`
Jinja2 for controlled document templates.

### `api`
FastAPI/Uvicorn for a future HTTP interface.

### `browser`
Playwright Python for the optional Chromium browser tool. After installing this
extra, run `uv run playwright install chromium` on machines that execute browser
integration tests or use `hermes-edu chat --browser`.

### `langchain`
Optional only. LangGraph does not require LangChain. Add LangChain abstractions only where they measurably reduce adapter/RAG plumbing without taking ownership of the architecture.

## Development

Ruff, Pyright, Pytest, coverage, pre-commit, build, MCP CLI, and pip-audit.

## Version policy

`pyproject.toml` constrains compatible major versions. `uv.lock` records exact resolved versions and should be committed after resolution. Dependabot and CI surface dependency drift; updates should be reviewed rather than blindly merged.
