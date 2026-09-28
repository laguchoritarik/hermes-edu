# 0012 — Structured TD content and text-only TeX rendering

Status: **Accepted**
Date: 2026-09-27

## Context

Model-authored LaTeX can perform filesystem I/O or shell-adjacent actions and is difficult to validate completely. v0.1 needs a safe artifact path and reproducible template.

## Decision

The model returns validated JSON for plans, exercises, sources, and audits. It does not author executable TeX. A versioned Jinja2 template renders all model text through a TeX escaping filter. Static validation checks the final source and a fixed XeLaTeX command runs with shell escape disabled, a timeout, and workspace confinement. The output PDF is reopened and checked before reporting success. Rendering and compilation are separate application-port operations and graph nodes.

## Consequences

The v0.1 template renders formulas as escaped text; polished display mathematics requires a future narrowly defined math-content contract. A PDF requires a local TeX installation and the rag extra for inspection. A `.tex` artifact can be generated explicitly without compilation via `--tex-only`.

## Alternatives considered

Passing raw model LaTeX to the compiler was rejected because command filtering alone is not a complete TeX sandbox. External PDF services were rejected for the local-first milestone.
