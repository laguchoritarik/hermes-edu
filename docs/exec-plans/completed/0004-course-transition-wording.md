# Course transition wording — implementation and validation

Scope confirmed by the user: harmonize transition expressions in examples and exercise solutions only. Do not replace the mathematical substance of sentences. Preserve formulas, equalities and inequalities exactly.

## Implemented

- Optional UTF-8 phrase bank through `course --phrases-file`; 30 expressions from six course chapters/resources by Garcin, Prost and Vienney, with page provenance. Vienney resources found are MP2I and are labelled accordingly.
- Durable `adapt_wording` and `verify_wording` nodes after mathematical audit/correction and before rendering. No-change proposals also require verification.
- Model selects exact spans and list indices; deterministic code applies edits and protects mathematical spans, surrounding prose, structure and citations. A refusal stops before rendering.
- Checkpoint contains the original phrase list, source path and hash. Resume does not reread an external file.
- DeepSeek handles both wording steps; DeepInfra remains reserved for mathematical audit and correction.

## Live observations, 2026-09-27

The first synthetic smoke selected an incorrect transition (consequence replaced by `Or`). Verification rejected it and no PDF was rendered. The selection instructions were clarified to distinguish consequence, premise/contrast and equivalence.

The second smoke changed `Par conséquent` to `Donc`, preserved both algebraic formulas exactly, passed DeepSeek verification and compiled a two-page PDF with pdfLaTeX. Both PDF pages were rendered and visually inspected. The checkpoint retained all three successful model responses (including a schema retry); estimated cost was USD 0.000272352. This smoke covers the wording nodes and rendering only, using explicitly synthetic content. It does not certify the separate MP course still undergoing mathematical/source audit.

A fresh-process smoke also exposed an eager type import that initialized LangGraph serialization before strict-msgpack setup. The import is now guarded by `TYPE_CHECKING`; a subprocess regression covers that boundary.

## Limits

Inserted phrases and formula preservation have deterministic checks. Transition identification, whether every liaison has been covered, and semantic equivalence remain model judgments. There is no automatic repair loop after a failed semantic wording verdict. The negative verdict and its usage are saved; resuming cannot ask the judge again until it approves. The workflow stops rather than publish the rejected candidate. Transient provider failures remain retryable.

The final phrase bank was checked against locally downloaded/read PDF page text for all 30 entries. Historical Vienney URLs for chapters 7/15 returned 404 and were replaced with currently available chapters 1/2 (2026–2027); no unverifiable historical page references remain. All six source PDFs have SHA-256 hashes recorded in the provenance file.

## Completed checks

`make lint`, `make typecheck`, `make test` (89 passing tests), `make build` and `make audit` completed successfully. The package itself is not listed on PyPI and pip-audit reports it as unauditable; no known vulnerability was reported for the audited dependencies. The source-grounded MP course validation remains tracked separately in plan 0003.
