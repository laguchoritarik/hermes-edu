# 0003 — Use LangGraph for orchestration

Status: **Accepted**  
Date: 2026-09-27

## Context

Hermes needs state, conditional routing, loops, checkpoints, pause/resume, and human approval.

## Decision

LangGraph is confined to the orchestration layer rather than domain/application models.

## Consequences

This decision creates a stable boundary for early implementation. Any reversal should be documented by a superseding ADR.

## Alternatives considered

Alternatives will be expanded when implementation evidence justifies revisiting the decision.
