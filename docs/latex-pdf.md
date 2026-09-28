# LaTeX and PDF pipeline

Planned deterministic pipeline:

1. build document model/content;
2. render through a controlled template;
3. validate obvious forbidden constructs/paths;
4. write source under workspace;
5. run a fixed LaTeX engine with timeout and controlled flags;
6. capture stdout/stderr/logs;
7. parse compilation diagnostics;
8. verify expected PDF exists and is non-empty;
9. inspect page count and extracted text for suspicious raw math/glyph artifacts;
10. return artifact metadata to workflow.

Model-generated shell commands must never be executed directly. Unrestricted `--shell-escape` is not part of the default design.

## v0.1 implementation

The model emits structured plain text. `td_v1.tex.j2` escapes every model-authored field; static validation rejects TeX I/O commands. The compiler uses a fixed XeLaTeX executable and arguments, `-no-shell-escape`, a timeout and a workspace path check. The PDF is reopened for inspection before being returned. Course compilation additionally treats critical log warnings and suspicious extracted PDF text as compilation failures rather than relying on exit code alone. `--tex-only` makes a source artifact without claiming a PDF. See ADR 0012.

## Mathematical notation

The course math allowlist accepts the standard norm delimiter `\|`, including
`\|f\|_\infty` and `\left\|f\right\|`. It remains a fixed allowlist; it does not
permit arbitrary TeX commands or macros.

Course prose rendering explicitly preserves `$...$` and `$$...$$` spans before escaping surrounding text. Expressions such as `$M_n(K)$`, `$C^k(I,K)$`, `$1_E$`, `$\operatorname{Mat}_{\mathcal B}(f)$`, `$f\circ g$`, `$\lambda\cdot x$`, `$a^{\varphi(n)}$` and `$\overline{a}+\overline{b}=\overline{a+b}$` are regression-tested so math is not converted into raw text glyphs.
