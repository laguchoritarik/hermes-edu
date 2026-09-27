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
9. optionally inspect page count/metadata;
10. return artifact metadata to workflow.

Model-generated shell commands must never be executed directly. Unrestricted `--shell-escape` is not part of the default design.
