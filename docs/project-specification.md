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

### FR-02 Workflow routing
The system shall route requests to course, TD, DM, DS, correction, explanation, or audit workflows.

### FR-03 Curriculum retrieval
The system shall retrieve the curriculum corresponding to the requested educational context and retain source/provenance metadata.

### FR-04 Knowledge retrieval
The system shall retrieve only relevant chunks from indexed documents instead of injecting entire libraries into the model context.

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
The system shall support DeepSeek, DeepInfra, and OpenRouter adapters behind a common port. Provider selection may later use cost/capability policies.

### FR-12 Persistence
The system shall support local SQLite repositories and SQLite LangGraph checkpoints. Production-grade stores may be added as adapters later.

### FR-13 Observability
Important workflow transitions, provider requests, retries, retrieval decisions, tool execution, approvals, and compilation results shall be logged structurally without leaking secrets.

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
Curriculum → prerequisite/context retrieval → section plan → approval → section generation → cross-section audit → render.

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
- arbitrary internet/browser automation;
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
