# 0015 — Versioned semantic personal references

Status: **Accepted**
Date: 2026-09-27

## Context

ADR 0011 covers a small synthetic TD corpus with SQLite JSON vectors. User-owned mathematical PDF references need durable deduplication, semantic object boundaries and fast bounded retrieval without changing that working TD path.

## Decision

Use the existing application ports and `EmbeddingPort`. The new `ReferenceLibrary` use case coordinates PDF acquisition, parser/OCR, `MathSemanticChunker`, embeddings, the SQLite reference repository and an hnswlib vector adapter. SHA-256 gives stable content identity. Version fingerprints control stage invalidation and persisted parsed/chunk artefacts avoid repeated work. SQLite is authoritative for document states, provenance, relations, caches and vector labels; model/dimension/version-scoped native HNSW files own vectors. `READY` requires all saved chunks and indexed vectors to agree. Search uses only semantic vector similarity, optional metadata scopes, per-call bounded top_k, and a configurable evidence threshold. A selected hit can then request its linked proof or solution. MCP/CLI only call the application use case.

## Consequences

The production reference parser now defaults to mandatory iLoveMyLaTeX PDF-to-LaTeX conversion before chunking, following the user's updated requirement. `HERMES_REFERENCE_PDF_MODE=text` explicitly selects the legacy/local path for offline use. Conversion mode/version changes invalidate parsed artifacts on import/reindex; queries do not trigger conversion. Raw converted LaTeX is retained in the existing parsed JSON cache, with full document page ranges when the service gives no per-page mapping. Missing conversion credentials fail only when new conversion is necessary; valid cached conversions remain reusable.

No Qdrant service is needed for the local reference library. The TD store remains compatible and separate. Native HNSW writes and SQLite commits cannot share one physical transaction, so incomplete imports never claim `READY`; retries reconcile saved labels/vectors and completed stage caches. The 0.35 initial relevance threshold must be calibrated for the actual embedding corpus. Source PDF retention costs local disk space but enables explicit reindexing.

## Alternatives

Fixed token windows lose mathematical boundaries. BM25/FTS would violate the requested 100% semantic content ranking. Replacing the TD retrieval store or requiring Qdrant would disturb the existing local workflow without a measured need.
