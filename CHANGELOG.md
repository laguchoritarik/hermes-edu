# Changelog

All notable changes will be documented here.

The project follows Semantic Versioning once the public API stabilizes.

## [Unreleased]

### Added
- Initial architecture scaffold.
- Clean Architecture boundaries.
- LangGraph, MCP v2, RAG, provider, persistence, and document-pipeline placeholders.
- Runnable v0.1 TD and course workflows with checkpointed approval, targeted revision, LaTeX/PDF output, and deterministic quality reports.
- Conversational `chat`/`prompt` interface with a configurable Helper Agent, dynamic ToolRouter, TaskDraft state, local FileSearchTool, optional BrowserTool, and skills discovery.
- Personal reference library with PDF ingestion, iLoveMyLaTeX conversion mode, semantic math chunking, HNSW retrieval, provenance, and CLI/MCP access.
- Task-based model routing and content-free provider outcome metrics for economical generation and stronger validation paths.
