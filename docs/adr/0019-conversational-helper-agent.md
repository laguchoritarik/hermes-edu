# 0019 — Conversational Helper Agent

Status: Accepted
Date: 2026-09-28

## Context

The first chat implementation incrementally updated `TaskDraft` with a
deterministic parser and a handful of command-like rules. That kept the workflow
safe, but it made natural requests such as "find my Fourier PDF, check Parseval
and add it to references" feel like a form instead of an educational agent.

Hermes already has the important deterministic pieces: `TaskDraft`, reference
library, HNSW search, browser service, providers, generators, validators,
quality gate and session persistence. The change needed is orchestration at the
conversation boundary, not a second business workflow.

## Decision

`ChatService` may use a configurable economical Helper Agent behind the existing
`LLMPort`. The helper receives a compact `AgentContext` and returns a validated
`AgentDecision`: `TOOL_CALL`, `TOOL_CALLS`, `UPDATE_STATE`, `ASK_USER`,
`DELEGATE`, `RESPOND` or `FINISH`.

`ToolRouter` selects a small set of relevant tool schemas from `ToolRegistry`.
Tool execution remains allowlisted deterministic code. Local skill cards are
exposed as compact strategy hints. The agent loop is bounded by
`HERMES_AGENT_MAX_STEPS`, stores compact observations and metrics in
`ChatSession`, and delegates ready generation or validation to existing Hermes
components.

The helper role is configured independently with `HERMES_HELPER_PROVIDER` and
`HERMES_HELPER_MODEL`. No provider/model ID is hardcoded in application or
domain logic.

## Consequences

The chat can assemble context across turns, correct imperfect user phrasing,
chain tools and preserve project defaults without replaying the whole raw
history. Slash commands and simple status/plan/source operations stay
deterministic fast paths.

The LLM decides intent, not authorization. Filesystem roots, browser
confirmations, reference policies, source coverage, workflow approval, validators
and quality gates remain enforced by code. Tool observations sent back to the
helper are compact summaries with IDs rather than full documents, HTML or logs.

## Alternatives considered

Keeping only deterministic parsing was simpler but too brittle for multi-tool
requests and contextual references like "the second one". Building a separate
multi-agent architecture was rejected because Hermes workflows, generators and
validators already provide the specialized execution layer.
