# 0011 — Versioned local retrieval for v0.1

Status: **Accepted**
Date: 2026-09-27

## Context

The first TD slice needs offline tests, bounded provenance-aware retrieval, and an optional remote embedding provider. The example corpus is small; ANN infrastructure would add an operational dependency without improving this milestone.

## Decision

Store normalized sources, stable chunks, content hashes, embedding model IDs, and JSON vectors in SQLite. Re-embed only changed or model-version-mismatched chunks. Retrieve by exact curriculum/track/subject/kind filter, then cosine similarity and top-k. Use a deterministic 256-dimensional feature-hash embedding by default for offline operation; use DeepInfra embeddings when configured. The two embedding spaces never mix because model IDs are recorded and filtered.

## Consequences

The local default is lexical in character and unsuitable for large corpora or cross-language semantic retrieval. JSON vector scanning is O(number of matching chunks). A later adapter can use sqlite-vec or another index behind the same retriever port, with an explicit migration/reindex plan. The synthetic MP source is clearly identified as non-official.

## Alternatives considered

A hosted vector database would weaken the local-first and offline-testable first slice. sqlite-vec ANN/index integration is deferred until corpus size or latency evidence justifies it.
