# 0005 — Provider-agnostic LLM port

Status: **Accepted**  
Date: 2026-09-27

## Context

The project needs DeepSeek, DeepInfra, OpenRouter and future provider switching.

## Decision

Provider-specific payloads live in adapters; use cases target a common port.

## Consequences

This decision creates a stable boundary for early implementation. Any reversal should be documented by a superseding ADR.

## Alternatives considered

Alternatives will be expanded when implementation evidence justifies revisiting the decision.
