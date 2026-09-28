# Files Manifest

This file inventories the original architecture scaffold. The v0.1 implementation status of changed modules is summarized below; modules not listed there retain their scaffold role.

| File | Purpose |
|---|---|
| `FILES_MANIFEST.md` | Complete inventory of the architecture scaffold and purpose of every file. |
| `.editorconfig` | Editor-neutral whitespace/encoding conventions. |
| `.env.example` | Complete environment/secrets/configuration template. |
| `.gitattributes` | Cross-platform line endings and binary file handling. |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | GitHub issue form configuration. |
| `.github/ISSUE_TEMPLATE/config.yml` | GitHub issue form configuration. |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | GitHub issue form configuration. |
| `.github/dependabot.yml` | GitHub collaboration/automation configuration. |
| `.github/pull_request_template.md` | GitHub collaboration/automation configuration. |
| `.github/workflows/ci.yml` | GitHub Actions automation. |
| `.github/workflows/security.yml` | GitHub Actions automation. |
| `.gitignore` | Ignore environments, secrets, local data, generated artifacts and caches. |
| `.pre-commit-config.yaml` | Local quality hooks using project-installed tools. |
| `.python-version` | Default Python version for uv/developers. |
| `CHANGELOG.md` | Human-readable change history. |
| `CODE_OF_CONDUCT.md` | Community behavior expectations. |
| `CONTRIBUTING.md` | Contributor setup and architecture rules. |
| `GOVERNANCE.md` | Architecture/maintainer decision process. |
| `LICENSE` | Default Apache-2.0 license for the public scaffold. |
| `Makefile` | Short developer commands for sync/check/test/audit/docs/build. |
| `README.md` | Primary project/architecture/developer onboarding document. |
| `SECURITY.md` | Vulnerability reporting and security baseline. |
| `data/README.md` | Local data directory documentation/placeholder; actual content is ignored. |
| `data/index/.gitkeep` | Local data directory documentation/placeholder; actual content is ignored. |
| `data/processed/.gitkeep` | Local data directory documentation/placeholder; actual content is ignored. |
| `data/raw/.gitkeep` | Local data directory documentation/placeholder; actual content is ignored. |
| `docs/adr/0001-clean-architecture.md` | Architecture Decision Record. |
| `docs/adr/0002-src-layout-and-uv.md` | Architecture Decision Record. |
| `docs/adr/0003-langgraph-orchestration.md` | Architecture Decision Record. |
| `docs/adr/0004-mcp-v2-boundary.md` | Architecture Decision Record. |
| `docs/adr/0005-provider-agnostic-llm.md` | Architecture Decision Record. |
| `docs/adr/0006-rag-separate-subsystem.md` | Architecture Decision Record. |
| `docs/adr/0007-sqlite-first.md` | Architecture Decision Record. |
| `docs/adr/0008-human-in-the-loop.md` | Architecture Decision Record. |
| `docs/adr/0009-security-by-default.md` | Architecture Decision Record. |
| `docs/adr/0010-apache-2-license.md` | Architecture Decision Record. |
| `docs/adr/README.md` | Architecture Decision Record. |
| `docs/architecture.md` | Developer architecture/specification documentation. |
| `docs/conventions.md` | Developer architecture/specification documentation. |
| `docs/data-model.md` | Developer architecture/specification documentation. |
| `docs/dependencies.md` | Developer architecture/specification documentation. |
| `docs/environment.md` | Developer architecture/specification documentation. |
| `docs/index.md` | Developer architecture/specification documentation. |
| `docs/langgraph.md` | Developer architecture/specification documentation. |
| `docs/latex-pdf.md` | Developer architecture/specification documentation. |
| `docs/llm-providers.md` | Developer architecture/specification documentation. |
| `docs/mcp.md` | Developer architecture/specification documentation. |
| `docs/project-specification.md` | Developer architecture/specification documentation. |
| `docs/rag.md` | Developer architecture/specification documentation. |
| `docs/roadmap.md` | Developer architecture/specification documentation. |
| `docs/security.md` | Developer architecture/specification documentation. |
| `docs/testing.md` | Developer architecture/specification documentation. |
| `examples/README.md` | Examples directory documentation; runnable examples come after stable APIs. |
| `mkdocs.yml` | Documentation-site navigation/configuration. |
| `pyproject.toml` | Package metadata, dependencies, extras, dependency groups, Ruff/Pyright/Pytest/Coverage config. |
| `scripts/README.md` | Maintainer scripts directory documentation. |
| `src/hermes_edu/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/__main__.py` | Architecture placeholder module; see its module docstring and architecture docs. |
| `src/hermes_edu/application/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/application/ports/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/application/ports/checkpointer.py` | Application-facing checkpoint/workflow persistence abstraction where needed. |
| `src/hermes_edu/application/ports/chat.py` | Application ports for chat sessions, project context, reference coverage and workflow execution. |
| `src/hermes_edu/application/ports/browser.py` | Provider-neutral browser automation port used by BrowserService. |
| `src/hermes_edu/application/ports/compiler.py` | Abstract document compiler/rendering port. |
| `src/hermes_edu/application/ports/embeddings.py` | Abstract embedding generation port. |
| `src/hermes_edu/application/ports/llm.py` | Text-only JSON LLM port, candidate routing and content-free outcome contracts. |
| `src/hermes_edu/application/ports/mcp.py` | Abstract gateway for MCP capabilities used by application code. |
| `src/hermes_edu/application/ports/repositories.py` | Abstract repositories for application data and sources. |
| `src/hermes_edu/application/ports/retriever.py` | Abstract knowledge retrieval port. |
| `src/hermes_edu/application/services/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/application/services/chat_intent.py` | Incremental deterministic parser from natural-language chat turns to `TaskDraft` deltas. |
| `src/hermes_edu/application/services/chat_tools.py` | Agent-facing Hermes tools for confined file search, reference/document search, draft markers, delegation markers and tool discovery. |
| `src/hermes_edu/application/services/context_builder.py` | Future service that assembles retrieval/model context from structured data. |
| `src/hermes_edu/application/services/document_quality.py` | Deterministic quality gate for generated educational documents. |
| `src/hermes_edu/application/services/helper_agent.py` | Conversational Helper Agent, structured decision parsing, deterministic fallback, draft patching and compact observation helpers. |
| `src/hermes_edu/application/services/provider_selector.py` | Future provider/model selection policy service. |
| `src/hermes_edu/application/services/tools.py` | Allowlisted tool registry, compact tool specs, discovery and dynamic `ToolRouter` for chat/MCP adapters. |
| `src/hermes_edu/application/services/validation.py` | Cross-use-case validation coordination placeholder. |
| `src/hermes_edu/application/use_cases/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/application/use_cases/audit_document.py` | Document audit use-case placeholder. |
| `src/hermes_edu/application/use_cases/browser.py` | BrowserService and BrowserTool over the BrowserPort boundary. |
| `src/hermes_edu/application/use_cases/chat.py` | Reusable conversation facade used by CLI chat/prompt and future MCP/web adapters. |
| `src/hermes_edu/application/use_cases/correct_exercise.py` | Exercise correction use-case placeholder. |
| `src/hermes_edu/application/use_cases/create_course.py` | Source-grounded course planning, generation, audit and targeted revision. |
| `src/hermes_edu/application/use_cases/create_dm.py` | DM/homework creation use-case placeholder. |
| `src/hermes_edu/application/use_cases/create_ds.py` | DS/test creation use-case placeholder. |
| `src/hermes_edu/application/use_cases/create_td.py` | TD/exercise-sheet creation use-case placeholder. |
| `src/hermes_edu/application/use_cases/explain_concept.py` | Concept explanation use-case placeholder. |
| `src/hermes_edu/application/use_cases/ingest_knowledge.py` | Knowledge ingestion use-case placeholder. |
| `src/hermes_edu/bootstrap.py` | Architecture placeholder module; see its module docstring and architecture docs. |
| `src/hermes_edu/config/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/config/paths.py` | Resolved/validated application paths and allowed roots. |
| `src/hermes_edu/config/settings.py` | Typed Pydantic settings loaded from environment. |
| `src/hermes_edu/documents/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/documents/latex/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/documents/latex/compiler.py` | Controlled LaTeX process wrapper. |
| `src/hermes_edu/documents/latex/renderer.py` | Controlled template-to-LaTeX renderer. |
| `src/hermes_edu/documents/latex/validator.py` | Static validation/security checks for generated LaTeX. |
| `src/hermes_edu/documents/models.py` | Document pipeline transfer/artifact/diagnostic models. |
| `src/hermes_edu/documents/pdf/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/documents/pdf/inspector.py` | PDF existence/page/metadata/validation inspection. |
| `src/hermes_edu/documents/pdf/metadata.py` | PDF metadata extraction model/adapter. |
| `src/hermes_edu/documents/templates/README.md` | Architecture placeholder module; see its module docstring and architecture docs. |
| `src/hermes_edu/documents/templates/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/documents/templates/repository.py` | Template repository abstraction/adapter. |
| `src/hermes_edu/browser/__init__.py` | Browser adapter package marker. |
| `src/hermes_edu/browser/playwright.py` | Playwright/Chromium browser adapter outside the application core. |
| `src/hermes_edu/domain/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/domain/enums.py` | Domain enumerations such as document/workflow/audit categories. |
| `src/hermes_edu/domain/errors.py` | Framework-independent domain exception hierarchy. |
| `src/hermes_edu/domain/models/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/domain/models/audit.py` | Structured audit issue/result domain models. |
| `src/hermes_edu/domain/models/agent.py` | Provider-neutral Helper Agent context, structured decisions, tool/skill specs, compact observations and metrics. |
| `src/hermes_edu/domain/models/browser.py` | Provider-neutral browser session, snapshot, element, download and trace models. |
| `src/hermes_edu/domain/models/chat.py` | Structured chat session, task draft, turn and response domain models. |
| `src/hermes_edu/domain/models/curriculum.py` | Learning context and curriculum-related domain models. |
| `src/hermes_edu/domain/models/document.py` | Document specification and generated artifact domain models. |
| `src/hermes_edu/domain/models/exercise.py` | Exercise, solution, concept, and difficulty domain models. |
| `src/hermes_edu/domain/models/quality.py` | Provider-neutral document quality, coverage and render report models. |
| `src/hermes_edu/domain/models/request.py` | Educational request and normalized intent domain models. |
| `src/hermes_edu/domain/models/source.py` | Source/provenance domain models. |
| `src/hermes_edu/domain/policies/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/domain/policies/curriculum_rules.py` | Pure curriculum compatibility policy rules. |
| `src/hermes_edu/domain/policies/document_rules.py` | Pure educational/document policy rules. |
| `src/hermes_edu/interfaces/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/interfaces/api/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/interfaces/api/app.py` | Optional FastAPI application composition surface. |
| `src/hermes_edu/interfaces/api/routes/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/interfaces/api/routes/generate.py` | HTTP generation route boundary. |
| `src/hermes_edu/interfaces/api/routes/health.py` | HTTP health/status route. |
| `src/hermes_edu/interfaces/cli/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/interfaces/cli/app.py` | Typer CLI application composition surface. |
| `src/hermes_edu/interfaces/cli/browser.py` | Debug CLI commands for the Browser Tool. |
| `src/hermes_edu/interfaces/cli/chat.py` | Terminal adapter for `hermes-edu chat` and `hermes-edu prompt`. |
| `src/hermes_edu/interfaces/cli/commands/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/interfaces/cli/commands/doctor.py` | CLI environment/dependency diagnostic command. |
| `src/hermes_edu/interfaces/cli/commands/generate.py` | CLI generation commands. |
| `src/hermes_edu/interfaces/cli/commands/ingest.py` | CLI ingestion/index commands. |
| `src/hermes_edu/knowledge/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/knowledge/chunking/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/knowledge/chunking/base.py` | Chunker abstraction. |
| `src/hermes_edu/knowledge/chunking/recursive.py` | Deterministic recursive chunking strategy. |
| `src/hermes_edu/knowledge/chunking/semantic.py` | Optional semantic chunking strategy. |
| `src/hermes_edu/knowledge/embeddings/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/knowledge/embeddings/base.py` | Embedding adapter base/helper. |
| `src/hermes_edu/knowledge/embeddings/deepinfra.py` | DeepInfra embedding adapter. |
| `src/hermes_edu/knowledge/ingestion/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/knowledge/ingestion/base.py` | Ingestion parser abstraction/normalization boundary. |
| `src/hermes_edu/knowledge/ingestion/latex.py` | LaTeX source ingestion adapter. |
| `src/hermes_edu/knowledge/ingestion/markdown.py` | Markdown ingestion adapter. |
| `src/hermes_edu/knowledge/ingestion/pdf.py` | PDF ingestion adapter. |
| `src/hermes_edu/knowledge/models.py` | Infrastructure/application transfer models for normalized documents/chunks/retrieval hits. |
| `src/hermes_edu/knowledge/retrieval/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/knowledge/retrieval/base.py` | Retriever implementation base/helper. |
| `src/hermes_edu/knowledge/retrieval/hybrid.py` | Future lexical + vector hybrid retrieval adapter. |
| `src/hermes_edu/knowledge/retrieval/rerank.py` | Optional reranking adapter. |
| `src/hermes_edu/knowledge/retrieval/vector.py` | Vector retrieval adapter. |
| `src/hermes_edu/knowledge/stores/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/knowledge/stores/base.py` | Knowledge/vector store abstraction helper. |
| `src/hermes_edu/knowledge/stores/schema.py` | Local knowledge store schema/version definitions. |
| `src/hermes_edu/knowledge/stores/sqlite.py` | SQLite/sqlite-vec knowledge store adapter. |
| `src/hermes_edu/llm/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/llm/base.py` | Shared provider adapter abstractions/helpers; application contracts remain in ports. |
| `src/hermes_edu/llm/models.py` | Infrastructure-level provider/model metadata definitions. |
| `src/hermes_edu/llm/providers/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/llm/providers/deepinfra.py` | DeepInfra provider adapter. |
| `src/hermes_edu/llm/providers/deepseek.py` | DeepSeek provider adapter. |
| `src/hermes_edu/llm/providers/openrouter.py` | OpenRouter provider adapter. |
| `src/hermes_edu/llm/registry.py` | Provider adapter registry. |
| `src/hermes_edu/llm/router.py` | Ordered task candidate routing, revision rotation and outcome observation adapter. |
| `src/hermes_edu/mcp/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/mcp/client.py` | MCP v2 client lifecycle/transport wrapper. |
| `src/hermes_edu/mcp/gateway.py` | Adapter implementing application MCP port using MCP v2 client(s). |
| `src/hermes_edu/mcp/prompts/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/mcp/prompts/correction.py` | MCP prompt definitions for correction/explanation workflows. |
| `src/hermes_edu/mcp/prompts/course.py` | MCP prompt definitions for course workflows. |
| `src/hermes_edu/mcp/prompts/dm.py` | MCP prompt definitions for DM workflows. |
| `src/hermes_edu/mcp/prompts/ds.py` | MCP prompt definitions for DS workflows. |
| `src/hermes_edu/mcp/prompts/td.py` | MCP prompt definitions for TD workflows. |
| `src/hermes_edu/mcp/resources/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/mcp/resources/courses.py` | MCP resources/resource templates for course/reference data. |
| `src/hermes_edu/mcp/resources/curriculum.py` | MCP resources/resource templates for curriculum data. |
| `src/hermes_edu/mcp/resources/templates.py` | MCP resources for document templates. |
| `src/hermes_edu/mcp/server.py` | Hermes MCP v2 server composition/registration surface. |
| `src/hermes_edu/mcp/tools/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/mcp/tools/compile_latex.py` | MCP tool adapter for controlled LaTeX compilation. |
| `src/hermes_edu/mcp/tools/search_knowledge.py` | MCP tool adapter for controlled knowledge search. |
| `src/hermes_edu/mcp/tools/validate_latex.py` | MCP tool adapter for LaTeX validation. |
| `src/hermes_edu/observability/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/observability/logging.py` | Structured logging configuration and redaction policy. |
| `src/hermes_edu/observability/metrics.py` | Optional metrics instrumentation boundary. |
| `src/hermes_edu/observability/tracing.py` | Optional tracing hooks/instrumentation boundary. |
| `src/hermes_edu/orchestration/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/orchestration/commands.py` | Future structured orchestration commands/decisions. |
| `src/hermes_edu/orchestration/context.py` | Run-scoped LangGraph context/service handles that must not be checkpointed as state. |
| `src/hermes_edu/orchestration/graphs/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/orchestration/graphs/correction.py` | Correction/explanation subgraph. |
| `src/hermes_edu/orchestration/graphs/course.py` | Checkpointed course graph with approval, section retrieval and bounded revision. |
| `src/hermes_edu/orchestration/graphs/dm.py` | DM subgraph. |
| `src/hermes_edu/orchestration/graphs/ds.py` | DS subgraph. |
| `src/hermes_edu/orchestration/graphs/ingestion.py` | Knowledge ingestion/indexing graph if orchestration is required. |
| `src/hermes_edu/orchestration/graphs/main.py` | Main workflow router graph. |
| `src/hermes_edu/orchestration/graphs/td.py` | TD subgraph. |
| `src/hermes_edu/orchestration/nodes/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/orchestration/nodes/analyze_request.py` | LLM/structured request analysis node. |
| `src/hermes_edu/orchestration/nodes/audit_document.py` | Audit node. |
| `src/hermes_edu/orchestration/nodes/compile_pdf.py` | PDF compilation coordination node. |
| `src/hermes_edu/orchestration/nodes/finalize_output.py` | Final artifact packaging/result node. |
| `src/hermes_edu/orchestration/nodes/generate_document.py` | Draft generation node. |
| `src/hermes_edu/orchestration/nodes/human_review.py` | Human-in-the-loop interrupt/resume node. |
| `src/hermes_edu/orchestration/nodes/plan_document.py` | Document planning node. |
| `src/hermes_edu/orchestration/nodes/render_latex.py` | LaTeX rendering coordination node. |
| `src/hermes_edu/orchestration/nodes/retrieve_curriculum.py` | Curriculum retrieval node. |
| `src/hermes_edu/orchestration/nodes/retrieve_knowledge.py` | RAG retrieval node. |
| `src/hermes_edu/orchestration/nodes/revise_document.py` | Revision node used in bounded loops. |
| `src/hermes_edu/orchestration/nodes/select_workflow.py` | Workflow selection preparation node. |
| `src/hermes_edu/orchestration/routing/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/orchestration/routing/approval_router.py` | Route human approval/revision/cancel outcomes. |
| `src/hermes_edu/orchestration/routing/audit_router.py` | Route audit success/revision/failure outcomes. |
| `src/hermes_edu/orchestration/routing/request_router.py` | Deterministic route from analyzed request to subgraph. |
| `src/hermes_edu/orchestration/state.py` | Typed LangGraph state schemas and reducers. |
| `src/hermes_edu/persistence/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/persistence/checkpoints/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/persistence/checkpoints/base.py` | Checkpoint factory/abstraction helper. |
| `src/hermes_edu/persistence/checkpoints/sqlite.py` | LangGraph SQLite checkpointer setup adapter. |
| `src/hermes_edu/persistence/model_outcomes.py` | SQLite content-free LLM outcome metrics and summary API. |
| `src/hermes_edu/persistence/migrations/README.md` | Architecture placeholder module; see its module docstring and architecture docs. |
| `src/hermes_edu/persistence/repositories/__init__.py` | Python package marker; public exports will be defined later. |
| `src/hermes_edu/persistence/repositories/base.py` | Repository adapter base/helper. |
| `src/hermes_edu/persistence/repositories/chat_json.py` | JSON session store for compact chat state under `.hermes/sessions`. |
| `src/hermes_edu/persistence/repositories/sqlite.py` | SQLite application repository adapter. |
| `skills/web_reference_research/SKILL.md` | BrowserTool-based workflow instructions for finding pedagogical web references and handing PDFs to the reference ingestion pipeline. |
| `tests/conftest.py` | Test scaffold / fixture / regression documentation. |
| `tests/e2e/.gitkeep` | Test scaffold / fixture / regression documentation. |
| `tests/fixtures/browser_site/index.html` | Local browser integration fixture with forms, scrolling, tabs and downloads. |
| `tests/fixtures/browser_site/result.html` | Local browser integration result page fixture. |
| `tests/fixtures/browser_site/fixture.pdf` | Tiny distributable PDF fixture for browser download and ingestion handoff tests. |
| `tests/fixtures/README.md` | Test scaffold / fixture / regression documentation. |
| `tests/golden/README.md` | Test scaffold / fixture / regression documentation. |
| `tests/integration/.gitkeep` | Test scaffold / fixture / regression documentation. |
| `tests/integration/test_browser_playwright.py` | Local Playwright/Chromium browser workflow test using the fixture site. |
| `tests/test_scaffold.py` | Test scaffold / fixture / regression documentation. |
| `tests/unit/.gitkeep` | Test scaffold / fixture / regression documentation. |
| `tests/unit/test_browser_service.py` | BrowserService, BrowserTool, policy, tracing and ingestion handoff unit tests. |
| `tests/unit/test_browser_tool.py` | BrowserTool dispatch tests over a fake BrowserPort. |
| `workspace/README.md` | Generated artifact workspace documentation. |

## Implementation rule

Do not implement every placeholder at once. The first vertical slice should populate only the modules required for one end-to-end TD workflow while preserving these boundaries.

## v0.1 implemented roles and additions

The TD slice implements the domain request/context/source/exercise/document/audit models and `domain/models/usage.py`; provider-neutral LLM, retriever, embedding and document ports; `CreateTD` and bounded context building; typed environment/path handling; DeepSeek chat, dated pricing in `llm/models.py` and optional DeepInfra embeddings; local ingestion, chunking, deterministic embeddings, `knowledge/stores/sqlite.py` and `knowledge/retrieval/vector.py`; the main and TD LangGraph graphs and typed checkpoint codecs; a strict SQLite checkpointer; versioned TD rendering, validation, controlled compilation and PDF inspection; the Typer CLI; and MCP v2 server capabilities. Other placeholder modules remain future-slice boundaries.

New files: `documents/latex/pipeline.py`, `documents/templates/td_v1.tex.j2`, `domain/models/usage.py`, `examples/curriculum/math-mp-reduction.md`, `docs/operations-v01.md`, ADRs 0011-0014, `docs/exec-plans/`, and unit/integration/e2e tests. `uv.lock` records the resolved environment.

## Personal-reference slice

`domain/models/reference.py` defines provider-neutral documents, mathematical blocks/chunks and search outcomes. `application/ports/references.py`, `application/services/reference_fingerprints.py` and `application/use_cases/reference_library.py` own boundaries, version decisions and use cases. `knowledge/ingestion/structured_pdf.py`, `ocr.py`, `reference_files.py`, `knowledge/chunking/semantic.py` and `knowledge/stores/hnsw.py` are replaceable adapters. `persistence/repositories/sqlite.py` and `persistence/migrations/0001_reference_library.sql` persist the registry and stage caches. `interfaces/cli/references.py` and `mcp/server.py` expose thin operations. `tests/integration/test_reference_library.py` covers the offline workflow. ADR 0015 records the storage/retrieval choice.

## Files intentionally not present yet

- a general-purpose migration framework: the reference-library migration is `persistence/migrations/0001_reference_library.sql` and is applied at first access without removing existing TD data.
- production Docker/deployment files: add after a stable runtime entry point exists.

## Course slice

`domain/models/course.py` defines request, plan, sections and audit issues. `application/ports/course.py` defines reference-search and document ports; `application/use_cases/create_course.py` owns bounded source-grounded steps. `application/services/structured_generation.py` shares accounted schema retries with TD. `orchestration/graphs/course.py` owns durable section checkpoints, approval and bounded repairs. `interfaces/cli/courses.py` exposes creation/resume; `interfaces/cli/curriculum.py` exposes embedded-query programme search. `documents/latex/course.py`, `math_content.py` and `templates/course_v1.tex.j2` render restricted math and compiled artifacts. `docs/courses.md` and ADR 0016 describe usage and boundaries. Course unit/integration/e2e tests exercise validation, safe rendering and offline workflow transitions.

The quality slice adds `domain/models/quality.py`, `application/services/document_quality.py`, course graph `quality_gate` integration, workspace `quality_report.json`/`quality_report.md` artifacts, deterministic render-quality checks, post-HNSW reference diversification, and regression tests in `tests/unit/test_document_quality.py`, `tests/unit/test_math_rendering.py`, and `tests/unit/test_reference_diversification.py`.

Plan sections retain their official curriculum passage IDs. The course use case builds bounded section queries from those passages and keeps programme scope separate from teaching citations in generation/audit. `docs/exec-plans/active/0005-pdf-latex-curriculum-grounding.md` records this change and mandatory iLoveMyLaTeX conversion with cached raw LaTeX in the existing parsed-reference model.

- `src/hermes_edu/domain/models/course_wording.py`: closed transition policy and protected math spans.
- `src/hermes_edu/application/use_cases/adapt_course_wording.py`: bounded transition selection and meaning verification.
- `examples/wording/transitions-cpge.fr.txt`: 30 allowed CPGE transition expressions.
- `examples/wording/transitions-cpge.sources.json`: phrase provenance and normalization.
- `docs/adr/0018-course-transition-wording.md`: optional course wording stage and guarantees.
- `tests/unit/test_course_wording.py`: deterministic wording protections and model refusal cases.
