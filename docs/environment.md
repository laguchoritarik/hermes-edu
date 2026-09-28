# Environment and local paths

Copy `.env.example` to `.env`. Real `.env` files are ignored.

## Directory classes

- `data/raw/`: local source documents.
- `data/processed/`: normalized/chunked intermediate data.
- `data/index/`: local retrieval indexes.
- `.local/`: databases/checkpoints and other machine-local runtime state.
- `workspace/`: generated artifacts for current runs.

None of these locations should contain public secrets or be assumed to exist on another contributor's machine.

The v0.1 CLI resolves these paths relative to its working directory unless configured as absolute paths. Keep `LANGGRAPH_STRICT_MSGPACK=true` before starting a checkpointed run. `HERMES_EMBEDDING_PROVIDER=deterministic` runs locally without an embedding key; `deepinfra` requires `DEEPINFRA_API_KEY` and `HERMES_EMBEDDING_MODEL`. Live generation requires the credential for every configured candidate. `HERMES_DEEPSEEK_TIMEOUT_SECONDS` and `HERMES_DEEPINFRA_TIMEOUT_SECONDS` default to 60; their attempt settings default to 3, while task fallback candidates are restricted to one transport and one empty-response attempt. `HERMES_COURSE_EXAMPLE_TOP_K` defaults to 6 example candidates before LLM selection. `HERMES_LLM_METRICS_DB_PATH` defaults to `.local/llm-metrics.db` and stores content-free model outcomes. `HERMES_CHAT_SESSIONS_DIR` stores compact chat session JSON; use the CLI `--auto-confirm` option when a ready prompt/chat task should run without an extra `/run`. Optional model price settings enable estimated cost; an aggregate is unknown if any call lacks a price.

The conversational Helper Agent is controlled by `HERMES_AGENT_ENABLED`,
`HERMES_AGENT_MAX_STEPS`, `HERMES_HELPER_PROVIDER`, `HERMES_HELPER_MODEL`,
`HERMES_HELPER_MAX_OUTPUT_TOKENS` and
`HERMES_HELPER_CONTEXT_TOKEN_BUDGET`. The helper context contains the latest
message, current `TaskDraft`, session summary, recent compact observations,
selected tool schemas and selected skills, not the full raw conversation.

Personal references accept input only inside `HERMES_DATA_DIR` and retain source PDFs under `HERMES_REFERENCE_DIR` for reindexing. `HERMES_DB_PATH` stores the reference registry and parsed/chunk caches alongside the existing TD tables; `HERMES_REFERENCE_HNSW_DIR` stores native HNSW index files. Set `HERMES_EMBEDDING_PROVIDER=deepinfra` and `HERMES_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B` for the requested DeepInfra Qwen3 embedding model. The default `HERMES_REFERENCE_PDF_MODE=latex` requires `ILOVEMYLATEX_API_KEY` for new conversions of all PDFs; successful converted LaTeX is cached and reused. Explicit `text` mode selects local extraction for offline use. The base URLs for DeepInfra, DeepSeek and iLoveMyLaTeX are configurable in `.env.example`. Reference size, chunk limits, embedding batch size, HNSW M/ef values, bounded top_k and relevance threshold are centralized there as well. Keep all credentials only in the ignored `.env`.

Course runs write `quality_report.json` and `quality_report.md` under `workspace/THREAD_ID/`. These reports may include source IDs and diagnostic summaries, but not API keys or full private documents.

`HERMES_REFERENCE_EMBEDDING_DIMENSION=0` accepts the dimension returned by the provider; a positive value validates the configured vector width.

## Browser settings

`HERMES_BROWSER_ENABLED=false` keeps browsing opt-in by default. CLI users can
enable it per session with `hermes-edu chat --browser` or run visible Chromium
with `--browser-visible`. Browser session files live under
`HERMES_BROWSER_SESSIONS_DIR` and downloads are kept in per-session
`downloads/` directories. `HERMES_BROWSER_MAX_STEPS` bounds agentic loops,
`HERMES_BROWSER_MAX_SNAPSHOT_CHARS` bounds observations, and optional
`HERMES_BROWSER_ALLOWED_DOMAINS` / `HERMES_BROWSER_BLOCKED_DOMAINS` constrain
navigation.

## Required local software

Base development: Python 3.12+, uv, Git.

LaTeX feature work: XeLaTeX/TeX Live. Exact packages will be documented once the first template is implemented.
