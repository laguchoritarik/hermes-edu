# 0001 — Use Clean Architecture / ports and adapters

Status: **Accepted**  
Date: 2026-09-27

## Context

Keep educational domain/application rules independent from frameworks and external providers.

## Decision

Adapters depend on application ports; the core does not import infrastructure.

## Consequences

This decision creates a stable boundary for early implementation. Any reversal should be documented by a superseding ADR.

## Alternatives considered

Alternatives will be expanded when implementation evidence justifies revisiting the decision.
