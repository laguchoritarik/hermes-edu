# Roadmap

## Phase 0 — architecture scaffold (this archive)
- repository layout;
- documentation/ADRs;
- dependency and environment declarations;
- CI/security baseline;
- placeholder module boundaries.

## Phase 1 — first vertical slice
- define actual domain schemas from tests;
- one LLM adapter;
- one local curriculum dataset;
- ingestion/chunking/embedding/retrieval;
- TD LangGraph subgraph;
- checkpoint + human plan approval;
- audit/revision loop;
- one LaTeX template and PDF compiler;
- CLI command;
- end-to-end/golden tests.

The implemented v0.1 slice uses a synthetic MP reduction source, deterministic offline feature-hash embeddings by default, optional DeepInfra embeddings, DeepSeek generation, checkpointed plan approval, and a controlled TD TeX template. XeLaTeX is an external runtime prerequisite. Formal mathematics verification, official curriculum content, richer notation, and additional workflows remain future work.

The personal PDF reference library is implemented as a subsequent slice: multi-file/directory import, content-hash deduplication, parser/chunker stage caches, PDF-to-LaTeX conversion through iLoveMyLaTeX with a retained LaTeX cache, math-aware chunking, batch embeddings, persistent HNSW search, metadata scopes, preferred/disabled references, explicit evidence outcomes, relation lookup, CLI/MCP operations and a SQLite migration. It remains an independently callable application service; automatic continuation inside the TD LangGraph after adding a missing source is future orchestration work.

## Phase 2 — architecture generalization
- task-based provider routing and bounded, validated fallback chains implemented; local model outcome summaries support manual model selection (ADR 0017);
- multiple curricula/tracks;
- DM/DS/correction subgraphs;
- course workflow implemented: programme retrieval after query embedding, a plan tied to official passage IDs, semantic PDF retrieval using each title and its official subpart, separate programme/teaching evidence, plan approval/resume, scoped audit, targeted repairs and restricted mathematical rendering (ADR 0016);
- conversational CLI and one-shot prompt interface implemented as adapters over `ChatService`, which persists structured sessions, updates `TaskDraft` incrementally, calls the reference library for `/add` and coverage checks, then runs the existing TD/course workflows;
- conversational Helper Agent slice: a configurable economical LLM role now orchestrates chat turns through structured decisions, dynamic tool routing, local skill cards, compact observations, bounded agent steps, metrics and delegation to existing workflows;
- richer audits;
- MCP exposure of stable capabilities.

## Phase 3 — reliability and community
- stronger evaluation suite;
- documentation site;
- plugin/provider contribution guides;
- production persistence adapter;
- API/UI only when needed.

Avoid multi-agent complexity until single-agent graph workflows are demonstrably insufficient.

The course workflow now optionally normalizes transition wording in examples and solutions against a file-backed closed list (ADR 0018). A saved negative semantic verdict cannot be overturned by repeatedly resuming the same request. A live synthetic DeepSeek-to-PDF smoke demonstrates this stage; the full source-grounded MP course remains an independent release validation gate.
