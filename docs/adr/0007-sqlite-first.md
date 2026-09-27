# 0007 — SQLite first for local persistence

Status: **Accepted**  
Date: 2026-09-27

## Context

The initial system is local-first and should be easy to install.

## Decision

Use SQLite for application data/index prototypes and LangGraph checkpoint SQLite adapter; permit production adapters later.

## Consequences

This decision creates a stable boundary for early implementation. Any reversal should be documented by a superseding ADR.

## Alternatives considered

Alternatives will be expanded when implementation evidence justifies revisiting the decision.
