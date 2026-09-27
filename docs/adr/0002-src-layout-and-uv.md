# 0002 — Use src layout and uv

Status: **Accepted**  
Date: 2026-09-27

## Context

The repository is intended to become a distributable Python project with reproducible developer environments.

## Decision

Use `src/hermes_edu`, `pyproject.toml`, uv dependency groups, and commit `uv.lock` after resolution.

## Consequences

This decision creates a stable boundary for early implementation. Any reversal should be documented by a superseding ADR.

## Alternatives considered

Alternatives will be expanded when implementation evidence justifies revisiting the decision.
