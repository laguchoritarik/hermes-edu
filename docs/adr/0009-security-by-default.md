# 0009 — Security controls are architectural defaults

Status: **Accepted**  
Date: 2026-09-27

## Context

Hermes consumes untrusted documents and model output and may invoke tools/compilers.

## Decision

Validate model outputs, restrict paths/tools, harden checkpoint deserialization, and sandbox/limit document compilation.

## Consequences

This decision creates a stable boundary for early implementation. Any reversal should be documented by a superseding ADR.

## Alternatives considered

Alternatives will be expanded when implementation evidence justifies revisiting the decision.
