# Course generation execution plan

Implement and run a thin course slice against the user's three local MP PDF references.

1. Add immutable course request/plan/section/audit models, reference-search and course-document ports.
2. Generate sections from bounded provenance-bearing reference context; validate structured responses and repair only audited sections.
3. Add durable LangGraph approval/resume and a CLI course command without changing TD behavior.
4. Render escaped text with a restricted math grammar, compile under existing restrictions, inspect PDF.
5. Add deterministic offline contracts, graph and CLI tests; run lint, typecheck, tests, build and dependency audit.
6. Run the implemented command on the imported references and inspect the final course.

The repository has pre-existing uncommitted implementation changes; preserve them. No official curriculum PDF was supplied: references are teaching sources, not official curriculum certification.

## Added acceptance criteria

- Each newly generated or corrected block cites a retrieved supporting passage; unsupported examples/proofs must be removed or supplied with evidence.
- Audit/correction use configured economical DeepInfra reasoning; post-correction verification returns to DeepSeek.
- Optional transition wording uses a closed file-backed phrase bank, only in examples and solutions; formulas and other prose are preserved. Add durable adaptation/verification nodes, offline regression tests and a live smoke test.
- Collect 30 distinct liaison expressions from several CPGE chapters by Laurent Garcin, Mickaël Prost and Mathieu Vienney, with page provenance.
- The actual MP course is still under mathematical/source review; do not describe it as an approved v0.1 deliverable before the live workflow and PDF checks complete.

## Latest live course result — 2026-09-27

The scoped DeepInfra audit completed all six sections. The subsequent first new correction failed after the adapter's three bounded attempts with `APITimeoutError`. The checkpoint remains at `revise`; the three earlier repairs and all six completed audits are retained. No validated full-course PDF has been emitted. Six recorded DeepInfra audit responses total about USD 0.098 estimated; timeouts may have unknown billing. The course is not an approved v0.1 deliverable. A next run should investigate provider latency/request size before retrying the saved correction, then complete mathematical/source checks, optional transition wording, compilation and visual PDF review.

The closed phrase bank and optional wording nodes are complete and validated separately; see completed plan 0004. Their successful synthetic PDF smoke must not be presented as the MP course.
