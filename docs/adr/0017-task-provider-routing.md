# 0017 — Provider routing for mathematical review

Status: Accepted
Date: 2026-09-27

## Context

The first real MP course run exposed incorrect mathematics, misnumbered audit targets and expensive whole-document reasoning. The user explicitly requested a stronger DeepInfra model for audit and correction while retaining economical initial generation.

## Decision

The composition root chooses provider adapters per task. `TaskRoutedLLM` builds an ordered candidate list for `audit`, `revise`, `plan` and `generate`; `verify` inherits the generation list. A fallback CSV permits at most four distinct alternatives and cannot repeat the preferred model. A timeout, provider error or invalid structured result advances through the list once. Revision attempts use `candidate_offset` modulo the candidate count, while the configured order remains fixed. DeepSeek and DeepInfra use 60-second timeouts; with fallbacks each candidate has one transport and one empty-response attempt before the next candidate. Credentials and model choices remain outside domain models.

The course graph audits one section at a time, with explicit section index/title validation and durable checkpoints. Once the initial sweep completes, it repairs only the targeted section and verifies only that section using the generation candidate list (`verify`), preserving findings for others. The global revision budget remains enforced. Every audit sees the course outline and official curriculum context; it is a section review, not a formal proof or an exhaustive cross-document consistency verifier.

## Consequences

The larger review model sees less context per call, and successfully reviewed sections are not sent repeatedly. `SQLiteModelOutcomeStore` records content-free task/provider/model outcomes in `.local/llm-metrics.db`; `summary()` supports manual latency and validation recommendations, never automatic routing changes. A live quality evaluation and independent review are still necessary: schema checks alone cannot establish mathematical correctness. Model/provider rate metadata is adapter configuration, not a domain dependency.

The generation and review prompts require fidelity to retrieved teaching references; missing evidence must be signalled rather than filled from model memory. Every scoped audit receives its section references.
