# Hermes Edu — Initial Project Specification (Cahier des charges)

## 1. Purpose

Hermes Edu is an open-source educational agent intended to help educators create, revise, audit, and produce structured pedagogical material while preserving human control and source traceability.

The initial specialization is mathematics. The architecture must support later extension to other disciplines without rewriting the orchestration or infrastructure layers.

## 2. Primary capabilities

Hermes should eventually support:

- course creation and revision;
- TD/exercise-sheet creation;
- DM/homework creation;
- DS/test creation;
- exercise correction and explanation;
- document audit (mathematics, pedagogy, curriculum alignment, statement/solution consistency);
- retrieval of official curricula, course notes, templates, and exercise banks;
- LaTeX source generation and deterministic PDF compilation;
- checkpointed long-running workflows;
- configurable human approval;
- multiple LLM providers;
- MCP tools/resources/prompts;
- local-first operation for core data.

## 3. Core user scenario

A user writes a natural-language request. The system:

1. interprets document type, subject, level, curriculum/track, chapter, constraints, and requested outputs;
2. selects a LangGraph workflow/subgraph;
3. retrieves authoritative curriculum material and relevant knowledge;
4. builds a document plan;
5. pauses for human approval when configured;
6. generates a structured draft;
7. audits it with deterministic checks and/or a model;
8. revises within a bounded loop;
9. renders LaTeX using a controlled template;
10. compiles and inspects PDF output;
11. returns source, PDF, provenance, and audit metadata.

## 4. Functional requirements

### FR-01 Request analysis
The system shall parse natural requests into validated structured intent. Unknown or ambiguous fields remain explicit rather than guessed silently.

### FR-01a Conversational interface
The system shall provide `hermes-edu chat` for multi-turn natural-language preparation and `hermes-edu prompt` for one-shot natural-language requests. Both interfaces shall update structured conversation state and converge to the same task/workflow contracts as structured CLI commands.

### FR-02 Workflow routing
The system shall route requests to course, TD, DM, DS, correction, explanation, or audit workflows.

### FR-03 Curriculum retrieval
The system shall retrieve the curriculum corresponding to the requested educational context and retain source/provenance metadata.

### FR-04 Knowledge retrieval
The system shall retrieve only relevant chunks from indexed documents instead of injecting entire libraries into the model context.

If required references are absent or insufficient, the system shall ask for an additional reference as workflow state. It shall not invent missing mathematical content and shall not write RAG/source-limitation comments into student-facing documents.

### FR-05 Planning
Document workflows shall create an explicit plan before long-form generation.

### FR-06 Human review
The system shall support pause/resume approval points using persistent LangGraph checkpoints.

### FR-07 Generation
Generation shall be provider-agnostic and use validated model outputs when the result controls execution.

### FR-08 Audit and revision
Generated material shall pass one or more audits. Revision loops shall be bounded by configuration.

### FR-09 Document pipeline
The system shall produce controlled LaTeX source and compile it using deterministic tooling. Compilation errors shall be captured as structured diagnostics.

### FR-10 MCP
Hermes shall be able to expose selected capabilities as MCP tools/resources/prompts and consume external MCP servers without coupling core logic to MCP.

### FR-11 Provider routing
The system shall support DeepSeek, DeepInfra, and OpenRouter adapters behind a common text-only JSON port. Task-specific ordered fallback candidates shall contain at most four distinct alternatives and exclude the preferred model; timeout, provider failure and invalid structured output advance to the next candidate. Observed latency and validation outcomes may inform manual configuration, never automatic candidate reordering. Aggregate cost is unknown when any constituent call lacks a cost estimate.

### FR-12 Persistence
The system shall support local SQLite repositories and SQLite LangGraph checkpoints. Production-grade stores may be added as adapters later.

Conversation sessions shall persist compact structured state, including turns, draft task, selected sources, pending questions and produced artifacts. They shall not persist full prompt transcripts as canonical workflow state.

### FR-13 Observability
Important workflow transitions, provider requests, retries, retrieval decisions, tool execution, approvals, and compilation results shall be logged structurally without leaking secrets.

### FR-14 Conversational interface
Hermes shall provide `hermes-edu chat` for multi-turn natural-language
preparation and `hermes-edu prompt` for one-shot natural-language requests. Both
interfaces shall converge to structured task state and existing application
workflows rather than implementing separate generation logic. Chat state shall
store compact structured data (`TaskDraft`, selected sources, pending questions,
artifacts) and avoid replaying the whole conversation for simple updates.

The conversational interface shall use a configurable economical Helper Agent
for natural-language orchestration. The helper shall receive compact context,
return structured decisions, update `TaskDraft` incrementally, select and chain
allowed tools, use local skills, ask one concise clarification when ambiguity is
material, and delegate generation or validation to existing Hermes components.
It shall not bypass reference coverage, filesystem, browser, approval, validator
or quality-gate policies.

### FR-15 Browser tool
Hermes shall optionally control a real browser through a provider-neutral
BrowserPort and a general BrowserTool usable from CLI, chat and MCP. Browser
observations shall be compact and structured, with temporary element references
instead of raw HTML. Downloads may be added to the personal reference library
only through the existing ingestion pipeline.

## 5. Non-functional requirements

### Maintainability
- Clear dependency direction.
- Small focused modules.
- No framework leakage into domain logic.
- ADR required for major architectural changes.

### Testability
- Ports must make provider/network/filesystem behavior replaceable by fakes.
- Unit tests must run offline.
- Golden educational regression tests must be possible.

### Security
- Secrets never committed.
- LLM output treated as untrusted.
- MCP tools allowlisted.
- Filesystem roots restricted.
- Checkpoint deserialization hardened.
- Generated LaTeX compiled without unrestricted shell escape.

### Portability
- Linux is the primary development target.
- Python-level design should remain portable to Windows/macOS where dependencies support them.

### Reproducibility
- `pyproject.toml` is authoritative for dependencies.
- `uv.lock` is committed once generated.
- model/provider configuration is explicit.

### Cost control
- Routing calls should use economical models where possible.
- RAG reduces context size.
- expensive reasoning models should be selected by policy, not as a universal default.
- Chat intent updates should use deterministic parsing or small structured
  extraction before invoking stronger generation/review models.

## 6. Architectural constraints

- Python 3.12+.
- LangGraph orchestrates workflows.
- MCP Python SDK v2.
- Domain and application logic must remain usable without MCP.
- LangChain is optional, not a core dependency.
- SQLite is the first local persistence backend.
- Provider APIs are accessed through adapters.
- `src/` package layout.

## 7. Initial entities

The domain should eventually represent at least:

- `EducationalRequest`;
- `LearningContext`;
- `DocumentSpec`;
- `Exercise`;
- `SourceReference`;
- `RetrievedChunk`;
- `AuditIssue`;
- `Artifact` / output metadata.

Fields are intentionally not frozen by this scaffold; the first vertical implementation will define them through tests and ADRs.

## 8. Planned workflows

### Main graph
Request analysis → workflow routing → subgraph → final artifacts.

### TD subgraph
Curriculum → RAG → plan → approval → generate → audit → revise loop → LaTeX → PDF.

### Course subgraph
Curriculum → prerequisite/context retrieval → section plan → approval → section generation → draft render → cross-section audit/revision → final render/compile.

### Correction subgraph
Parse statement/submission → identify expected method → mathematical verification → pedagogical feedback → corrected solution → audit.

## 9. Human-in-the-loop policy

Approval points are configurable. Candidate checkpoints:

- plan approval before long generation;
- approval before destructive/externally visible actions;
- final document approval before publication/sharing.

An `interrupt()` node must avoid irreversible side effects before the interruption because the node may restart on resume.

## 10. RAG requirements

Each retrieved chunk should eventually include:

- stable identifier;
- document/source identifier;
- text;
- location metadata (page/section where available);
- educational context metadata;
- embedding/model version;
- ingestion timestamp/version;
- optional score/rerank score.

The retriever interface must not expose a specific vector database to use cases.

### Personal PDF reference library — implemented scope

Users can add one PDF, several PDFs, or a directory of PDFs; list, inspect, disable, prefer, remove, and explicitly reindex a reference through CLI or MCP. A reference's SHA-256 content hash deduplicates identical bytes across filenames and paths. An import is considered complete only when parsed/chunk artifacts and every embedding vector are saved, the HNSW index contains them, and SQLite records `READY`. The durable registry records parser/OCR and chunker fingerprints, embedding model/dimension, index version, status, failure, title and provenance. Failed batch work can be resumed from saved artifacts; a parser change invalidates parsed and downstream data, a chunker change preserves parsed data, and a model change preserves parsed/chunk data. Original PDFs are retained locally for explicit reindexing.

The default reference pipeline converts each new PDF to LaTeX through iLoveMyLaTeX before semantic chunking, including PDFs with a text layer. The raw LaTeX is cached durably with the parsed document; unchanged successful imports do not repeat conversion. A missing key or a failed conversion raises an explicit ingestion error, without a silent local fallback. An explicit `text` mode remains available for offline extraction/tests. The parser recognizes chapters, sections, definitions, claims, proofs, remarks, examples, exercises, solutions and other math blocks. The semantic math chunker treats these blocks as primary boundaries; token limits are only safeguards for oversized blocks. It keeps statement/proof and exercise/solution links, source provenance and a separate context-enriched embedding text. If the conversion response contains no page mapping, converted chunks carry the full document page range rather than an invented exact page. An oversized proof is divided into numbered children at logical boundaries where possible. Unrelated objects receive no artificial overlap.

The registry also records the embedding provider and can enforce a configured vector dimension; the default detects dimension from the provider response.

Reference content search is semantic vector retrieval with a persistent cosine HNSW index, metadata filtering and a centralized relevance threshold. Per-call `top_k` is configurable and bounded. Preferred references are selected by scope, not a hidden similarity boost. The result carries a small set of scored chunks and one of `EMPTY_LIBRARY`, `NO_RELEVANT_SOURCE`, or `ENOUGH_EVIDENCE`. It retains the query so a caller may invite the user to add a missing PDF and retry the same request. Related proofs or solutions are loaded only when requested. SQLite owns business metadata/artefacts; HNSW files own vectors. A DeepInfra adapter supports `Qwen/Qwen3-Embedding-8B` without provider code in domain or use cases; offline tests use a fake. Automatic resumption of an interrupted TD LangGraph flow after adding a PDF is not part of this slice.

## 11. Provider requirements

Every LLM adapter must expose the same application-level capabilities. Provider-specific request fields must remain inside adapters. The provider registry/router may consider:

- task type;
- model capability;
- context length;
- structured-output support;
- tool calling support;
- cost policy;
- latency policy;
- availability/fallback policy.

## 12. MCP requirements

MCP server capabilities shall be thin adapters over application services. MCP tools must validate arguments and authorization/root restrictions. MCP resource enumeration must not automatically load large document bodies. Resource content should be loaded only when required.

The conversational core is exposed as `ChatService` so a future MCP tool can
start/resume sessions, add references, inspect status/plan/sources and run tasks
without depending on terminal `input()`/`print()`.

## 13. Document safety requirements

- generated file paths resolve under configured workspace roots;
- no arbitrary shell command execution from model output;
- LaTeX compiler invoked with fixed executable/options;
- shell escape disabled unless explicitly justified;
- compilation timeout enforced;
- logs captured and parsed;
- output PDF verified to exist and be non-empty before success.

## 14. Testing requirements

A feature is not complete without:

- unit tests for deterministic logic;
- integration tests for its adapter boundary;
- an end-to-end or golden test when it changes educational output;
- documentation or ADR if architecture changes.

## 15. First implementation milestone

Implement one end-to-end vertical slice only:

**Mathematics → one curriculum/track → TD generation → one provider → local RAG → approval → audit/revision → LaTeX/PDF.**

The purpose is to validate boundaries before expanding breadth.

## 16. Explicit non-goals for the first milestone

- multi-tenant SaaS;
- fully autonomous publishing;
- arbitrary unrestricted internet/browser automation;
- every educational system and subject;
- multi-agent swarms;
- sophisticated UI;
- premature distributed infrastructure.

## 17. Definition of architecture-ready

Before v0.1 implementation starts:

- repository scaffold committed;
- CI green;
- dependency lock generated;
- `.env.example` documented;
- architecture and ADRs reviewed;
- one issue/milestone describing the first vertical slice;
- coding/testing conventions agreed.

## Course slice — implemented

The course command requires an indexed curriculum identifier, computes the query embedding and retrieves programme evidence before planning. Each new plan section must name valid retrieved curriculum passage IDs. Its title, objective and official subpart form the bounded query for semantic search of the personal PDF library. Generation receives programme scope separately from teaching evidence; mathematical block citations must refer to the latter. Structured sections contain mathematical blocks and validated citations. The audit returns both section index and exact title, which must agree before any repair is routed. Durable checkpoints permit approval, rejection and retry without regenerating completed sections. Legacy plans without per-section curriculum IDs use the saved bounded programme context. The renderer supports an explicit mathematical grammar and controlled PDF compilation. See ADR 0016 and `docs/courses.md`.

### Reference fidelity and cost policy

Course creation must be grounded in retrieved references and retain their provenance. The model must not invent examples, proofs, hypotheses or constants to fill evidence gaps. Missing evidence must be signalled. The audit checks both mathematics and fidelity against the actual section references. Source use reduces error risk but does not eliminate reformulation errors.

DeepInfra escalation is configured per task. Use an economical reasoning model; after a targeted correction, `verify` uses the ordered generation candidates. Do not silently route the entire workflow through an expensive model.

### Quality assurance gate

Generated pedagogical documents must pass a quality gate before the final result is considered publishable. For the course workflow, the first implemented gate is deterministic and runs after audit/revision and rendering/compilation. It validates coverage against the approved plan and retained references, rejects internal RAG/source-gap comments in student text, detects source metadata contamination, flags raw math notation outside math delimiters, catches exact or near duplicate blocks, checks selected notation consistency such as `K` to `R` switches between statement and solution, and reports elementary mathematical red flags. Missing mandatory evidence is returned as a structured source gap asking for additional references; it must never be converted into a student-facing excuse. The report is written as `quality_report.json` and `quality_report.md`; any blocker marks the result `DRAFT`.
