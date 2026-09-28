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

## v0.1 coverage

The suite covers structured parsing, vector reuse/provenance, provider HTTP mapping through a mock transport, TeX escaping, MCP registration/validation, graph success, targeted revision, exhaustion, approval/resume, and a CLI run with synthetic knowledge and a scripted model. XeLaTeX-dependent compilation is only available when that external executable is installed.

## Personal-reference checks

The PDF conversion suite covers mandatory iLoveMyLaTeX conversion of text PDFs, raw PDF upload/status/result, missing-key failure without fallback, persisted LaTeX across restart/model change, cache repair, and parser-mode invalidation. Tests explicitly select local `text` mode or inject a fake converter; live API calls are not part of the automated suite.

`tests/integration/test_reference_library.py` uses small generated mathematical PDFs and a fake embedding provider. It covers block types/relations/pages, long proof splitting, content hash duplicates and renamed files, chunker/model/content invalidation, HNSW scoped search, bounded top_k, evidence outcomes, preference and disabling, linked content, physical deletion, failed-batch resume and concurrent duplicate import. These tests require no paid API; install the `rag` extra (`uv sync --all-extras --all-groups`). The native HNSW adapter is exercised locally, without Qdrant.

## Curriculum-guided course checks

`tests/unit/test_course_contracts.py` and `tests/e2e/test_course_graph.py` cover plan passage IDs, retention of the official subpart in bounded reference queries, separate programme/teaching contexts, rejection of curriculum-only mathematical citations, legacy checkpoints and filtered final provenance. CLI tests use scripted providers. Source-ID validation is deterministic; semantic fidelity of model-generated mathematics still requires the runtime audit and human review when appropriate.

Provider-routing tests use fake candidates to cover ordered CSV fallback after invalid JSON, timeout and provider failure; CSV limits and duplicate-preferred-model rejection; one fallback attempt per provider; revision candidate rotation; content-free outcome summaries; unknown aggregate cost; and the rule that contradictory audit findings or overlong new audit explanations do not autoapprove a draft. Legacy checkpoints remain readable. They do not call live providers.

## Quality gate checks

`tests/unit/test_document_quality.py` contains synthetic regressions for elementary mathematical red flags, `K` to `R` notation switches between statement and solution, duplicate definitions, missing source evidence, internal RAG comments in student text, source metadata contamination, raw math outside delimiters, blocker status and valid-pass status. `tests/unit/test_math_rendering.py` protects common algebra notation from text escaping. `tests/unit/test_reference_diversification.py` covers deterministic post-HNSW deduplication/diversification. The course graph e2e tests now assert `quality_report.json` and `quality_report.md` artifacts.

## Chat interface checks

`tests/unit/test_chat_service.py` covers multi-turn draft enrichment, project-context defaults, output add/remove edits, missing required fields, reference addition through the existing ingestion port, missing coverage requests, cached plan/status behavior, session resume, provider failures and quality-gate blockers. `tests/e2e/test_chat_cli.py` fakes `ChatService` at the CLI boundary so `hermes-edu chat` and `hermes-edu prompt` are tested without running a live workflow.

`tests/unit/test_helper_agent_chat.py` covers the agentic chat slice with fake
agents/tools: FileSearchTool and BrowserTool selection, multi-tool chaining,
observation-driven follow-up, progressive `TaskDraft` patches, project-context
defaults, clarification questions, dynamic ToolRouter filtering, deterministic
`/status`, max-step stop, recoverable tool errors, generator delegation,
metrics, filesystem confinement, compact reference observations and JSON session
summary restoration.

## Browser checks

`tests/unit/test_browser_service.py` and `tests/unit/test_browser_tool.py` use
fake browser ports to cover session reuse, open/read/click/fill/type/scroll,
select/check/press/wait, screenshots, downloads, tab actions, stale/timeout
error tracing, secret filtering, max step enforcement, domain blocking and tool
dispatch. `tests/integration/test_browser_playwright.py` serves a local HTML
fixture with inputs, textarea, checkbox, select, scrolling, a new tab and a PDF
download; it skips when Chromium has not been installed with Playwright.
