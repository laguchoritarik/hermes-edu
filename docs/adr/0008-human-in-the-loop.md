# 0008 — Human approval is a first-class workflow feature

Status: **Accepted**  
Date: 2026-09-27

## Context

Educational artifacts and external actions benefit from explicit review.

## Decision

Use persistent checkpoints plus LangGraph interrupts; irreversible side effects occur after approval nodes.

## Consequences

This decision creates a stable boundary for early implementation. Any reversal should be documented by a superseding ADR.

## Alternatives considered

Alternatives will be expanded when implementation evidence justifies revisiting the decision.
