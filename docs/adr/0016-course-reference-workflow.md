# 0016 — Source-grounded course workflow and restricted mathematical content

Status: Accepted
Date: 2026-09-27

## Context

Users need an actual course workflow tested against personal PDF references and an official programme. The TD path is implemented, but courses and automatic library use were placeholders. Escaping all mathematics as plain text (ADR 0012) is insufficient for a usable mathematics course.

## Decision

Add an independent CourseRequest/Plan/Section/Draft contract, application CreateCourse steps and a checkpointed course graph. The composition root wires two existing retrieval systems: programme chunks in SQLite filtered by curriculum, track, subject and kind; teaching references in the semantic PDF library. Both embed the query before vector retrieval. Programme ingestion accepts a canonical source URL retained in citations. The operator verifies that imported curricula come from an official publisher; a kind label alone is not an authenticity assertion.

Programme retrieval precedes planning. Every section retrieves a bounded set of reference chunks, retains page/document/chunk provenance, and generates validated JSON. References are data, never instructions. The model audits the course sections against the retrieved programme and teaching references (scoped audits are detailed in ADR 0017). Audit issues identify their target by both index and exact section title; mismatches fail validation rather than route a repair to the wrong section. Repairs replace only the identified section, within HERMES_MAX_REVISION_LOOPS. The graph checkpoints between section retrieval/generation and supports plan approval, rejection and continuation after a failed node. Workflow state contains serializable values only.

Each new planned section records validated `curriculum_source_ids`. The reference query includes that section's actual official subpart as well as its title and objective, with a shared 4 000 character bound and space reserved for programme text. Curriculum context and teaching evidence are selected independently: programme passages define scope, while mathematical blocks cite only teaching references. Source IDs exposed to the model are normalized to the same chunk IDs accepted by validation. Old plans without per-section programme IDs remain readable using their saved bounded official context; no database migration is needed for this optional serialized field.

Direct calls to `CreateCourse.generate` must supply nonempty official `curriculum` separately from teaching chunks; missing official context and overlapping programme/teaching chunk IDs fail validation. Scoped audits receive the same section-specific official basis as generation. The graph supplies these arguments from separate checkpoint fields, including when resuming a legacy plan.

A course renderer escapes prose and accepts mathematics solely between dollar delimiters under an explicit command allowlist and balanced-brace checks. It rejects macros, environments, TeX I/O and TeX alternate character encodings. This is a deliberately limited math contract, not arbitrary model-authored TeX. The deterministic preamble is compatible with pdfLaTeX and XeLaTeX. Existing no-shell-escape compilation, workspace confinement, hash checks and PDF inspection remain mandatory. TD rendering stays unchanged.

## Consequences

The CLI exposes course, course-resume and curriculum search. Curriculum selection is explicit; generation stops if suitable programme/reference evidence is missing. Downloading or asserting the authenticity of arbitrary web sources is not delegated to the model. Cost/usage accounting covers every returned model attempt; embedding accounting remains as implemented by the existing embedding adapter. Official programme alignment is model-audited, not a formal mathematical certification. Regression tests use offline ports; a real user execution exercises the configured providers separately.
