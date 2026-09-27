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

## Phase 2 — architecture generalization
- provider router/fallbacks;
- multiple curricula/tracks;
- course/DM/DS/correction subgraphs;
- richer audits;
- MCP exposure of stable capabilities.

## Phase 3 — reliability and community
- stronger evaluation suite;
- documentation site;
- plugin/provider contribution guides;
- production persistence adapter;
- API/UI only when needed.

Avoid multi-agent complexity until single-agent graph workflows are demonstrably insufficient.
