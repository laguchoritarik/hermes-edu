# 0006 — Keep RAG as a separate knowledge subsystem

Status: **Accepted**  
Date: 2026-09-27

## Context

Retrieval and indexing have different responsibilities from MCP and LLM orchestration.

## Decision

Ingestion, chunking, embeddings, stores and retrieval live under `knowledge/` behind ports.

## Consequences

This decision creates a stable boundary for early implementation. Any reversal should be documented by a superseding ADR.

## Alternatives considered

Alternatives will be expanded when implementation evidence justifies revisiting the decision.
