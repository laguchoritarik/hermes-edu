# 0018 — Closed-list transitions in course examples and solutions

Status: Accepted
Date: 2026-09-27

## Context

The user wants course wording based on a supplied, closed list of CPGE transition expressions. The clarified scope is transitions in examples and exercise answers, not definitions, substantive explanations or all prose. Mathematical formulas, equalities and inequalities must remain unchanged.

## Decision

An optional `--phrases-file` CLI argument reads a bounded UTF-8 file, one expression per line. The CLI validates the pure domain policy and checkpoints its phrases, file path and SHA-256. Resume uses that snapshot even if the original file changes or disappears.

After successful mathematical audit/repair, LangGraph runs `adapt_wording` then `verify_wording` for each eligible section. Adaptation is a separate application use case with the existing LLM port. It accepts structured edit locations and approved phrase indices, never replacement prose. Deterministic validation rejects unknown indices, overlapping edits, mismatched original text, edits outside `example`/`solution` blocks and edits touching protected `$...$`/`$$...$$` spans. Python applies the replacements, leaving every character outside the selected ranges unchanged. The section is committed only after verification.

Both wording selection and verification use the primary model (DeepSeek in the configured workflow). The verification checks whether changes are transitions, preserve logical meaning and respect the closed list. Even a `no_change` decision requires verification. A negative verdict stops before rendering. No free-text fallback, automatic escalation or unbounded repair loop is introduced. A transient verification failure can be resumed without repeating completed adaptations. A negative semantic verdict is persisted and cannot be changed by repeatedly resuming the same request.

## Consequences

Formula preservation and membership of inserted expressions in the allowed list are deterministic guarantees. Classification of prose as a transition, completeness of that classification and semantic equivalence remain model judgments, not formal guarantees. For example, replacing an opposition by a consequence is incorrect even though both expressions can be in the list. Existing courses without a phrase file follow the original graph path. Titles, definitions, theorems, proofs and exercise statements remain unchanged by this optional stage.

The example phrase bank records author, chapter and page provenance separately. It is a style vocabulary, not evidence for the course's mathematical claims; teaching references remain attached to individual content blocks.
