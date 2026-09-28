# Hermes Edu v0.1 operation and cost strategy

## Local run

Install all required extras with `uv sync --all-extras --all-groups`. Copy `.env.example` to `.env` only if it does not exist, set a valid DeepSeek key/model for live TD generation, and keep `LANGGRAPH_STRICT_MSGPACK=true`. The default deterministic embedding needs no credential. Index the bundled synthetic curriculum with `uv run hermes-edu ingest --example`. Run `uv run hermes-edu td "Reduction" --curriculum sample-mp --track MP --exercises 3`; then approve its plan with `uv run hermes-edu resume THREAD_ID approve`. Use `--yes` only when explicitly skipping approval. Use `--tex-only` if XeLaTeX is unavailable or a PDF is not desired.

User-provided files must be under `HERMES_DATA_DIR`. `ingest` accepts `.md`, `.txt`, `.tex` and bounded `.pdf` files. The bundled example is synthetic and does not assert official curriculum alignment. Index genuine licensed curriculum material before relying on a TD for curriculum compliance.

## Cost and context

The TD graph filters by curriculum/track and retrieves at most `HERMES_RAG_TOP_K` chunks of each kind. A context builder truncates at `HERMES_CONTEXT_TOKEN_BUDGET` using a conservative character estimate. Routing is deterministic; planning uses the default model with reasoning disabled by default. Generation and audit may use separate configured model IDs and reasoning efforts. Every returned call, including an empty JSON response retried once, records provider, model, task, input/output/cached tokens, latency and estimated USD cost. Price estimates use configured uncached input, cached input and output rates per million tokens. For the default `deepseek-flash` model, a provider-side table dated 2026-09-27 supplies peak/off-peak estimates when no override is configured; each record labels the price basis. Other models without configured rates, or calls without usage, report unknown cost. Check the [current DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) regularly because rates may change. The final CLI JSON exposes each call and totals.

Unchanged source chunks reuse stored embeddings. A completed plan is checkpointed before approval, so resume does not repeat that model call. Audit repair replaces only one affected exercise per revision. The configured loop bound prevents runaway calls. No MCP tool list or complete source library is sent to the model.

## Limits

The offline feature-hash embedding is useful for small lexical corpora, not semantic search at scale. A model audit does not prove mathematical correctness. The TD renderer escapes model text; the course renderer accepts a restricted mathematical grammar described in `docs/courses.md`. XeLaTeX (or configured pdfLaTeX for courses) and a suitable TeX Live package set are external dependencies for PDF output. TD and course workflows have dedicated CLI commands; unrestricted natural-language intent parsing remains a later slice.

## Personal PDF references

Install the `rag` extra with `uv sync --all-extras --all-groups`. Put PDFs under `HERMES_DATA_DIR`, then run `uv run hermes-edu references add data/file.pdf`, `uv run hermes-edu references add-directory data/books`, or the equivalent MCP tools. List and search with `uv run hermes-edu references list` and `uv run hermes-edu references search "query" --top-k 5`. To force a full rebuild, run `uv run hermes-edu references reindex DOCUMENT_ID`. The SQLite migration is automatic at first reference access and preserves existing TD tables. Back up `.local/hermes.db`, `.local/reference-files/` and `.local/reference-hnsw/` together.

Production reference embeddings use `HERMES_EMBEDDING_PROVIDER=deepinfra`, `HERMES_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B`, and `DEEPINFRA_API_KEY`. In the default `latex` mode, iLoveMyLaTeX converts each new PDF before chunking. The parser sends the PDF to the configured API endpoint and keeps the returned LaTeX in the persisted parsed artifact. Explicit `text` mode is available for offline local extraction. A normal search never reconverts a PDF. Search always returns a bounded set of semantic hits and a distinct empty/no-evidence outcome. Tune `HERMES_REFERENCE_MIN_SCORE` with a representative corpus before relying on it for abstention. HNSW M/ef and top_k limits live in `.env.example`.

The converter uses raw PDF upload with `Content-Type: application/pdf` and `X-Filename`, matching the user-provided API script, then polls status and retrieves LaTeX. On 2026-09-27, a live synthetic PDF completed successfully and returned 704 LaTeX characters. The earlier multipart request was rejected with HTTP 400; it is no longer the adapter contract. DeepInfra Qwen3 embedding and DeepSeek smoke calls also succeeded.

## Official programme and course scope

The course pipeline extracts a plan from official passages, then embeds each section's title/objective and corresponding programme subpart to retrieve teaching references. Planning, generation and scoped audit retain that correspondence. Programme and teaching contexts have separate budgets and citation roles; direct generation without programme context is rejected.

The requested live course excludes the MPSI refresher. Two preliminary plans were rejected for scope; thread `integrales-generalisees-mp-final-20260927` has three saved sections and a draft `workspace/THREAD_ID/course.tex`. A nine-page PDF was compiled after a clean model audit, but visual review found mathematical errors from damaged extracts and a faulty proof. Those findings were sent back to Hermès. The run subsequently reached its ten-revision limit with one unsupported variable-interval integration method in section 3. The latest draft TeX is retained; `course-draft.pdf` is the earlier, non-final compilation and does not represent the latest TeX. `draft-status.json` records the remaining issue. No final PDF is claimed.

## Slow or invalid model responses

Course generation and audit use bounded section contexts and durable checkpoints. Configure ordered alternatives with `HERMES_AUDIT_FALLBACK_MODELS`, `HERMES_REVISION_FALLBACK_MODELS`, `HERMES_PLAN_FALLBACK_MODELS` and `HERMES_GENERATION_FALLBACK_MODELS`; verification shares the generation alternatives. The same parser validates every candidate. A reported mathematical defect still requires correction; changing provider never approves it automatically.

The local evaluation replaced the slow Qwen3.5-397B audit with smaller candidate models. Observed Next80 section audits took approximately 7–12 seconds and repairs 10–21 seconds, compared with 332 seconds for one 397B audit. These are small, task-specific samples, not guaranteed performance or mathematical quality. Qwen3.5-35B repeatedly timed out or consumed an earlier 8,000-token budget without usable JSON, so it was replaced in the configured fallback lists with `Qwen/Qwen3-235B-A22B-Instruct-2507`. The local configuration uses 235B for initial audit and Next80 for revision, with alternatives documented in `.env.example`. The output limit is 16,000. Both providers have configurable timeouts; configured fallback tasks use one transport attempt per candidate. See `docs/llm-providers.md`.

New calls record content-free model outcomes in `HERMES_LLM_METRICS_DB_PATH` (default `.local/llm-metrics.db`). Inspect the observations before changing preferences:

```bash
uv run python -c 'from pathlib import Path; from hermes_edu.persistence.model_outcomes import SQLiteModelOutcomeStore; [print(row) for row in SQLiteModelOutcomeStore(Path(".local/llm-metrics.db")).summary()]'
```

`validated` means the response passed the application parser; it does not establish mathematical correctness. Unknown provider charges and calls from before metrics were enabled are not reconstructed. The configured order is not automatically changed by these statistics.

For this course, reliable source extraction and review of the remaining section-3 passage are still needed. Do not reset the revision counter or compile the latest draft to present an unresolved audit as success.
