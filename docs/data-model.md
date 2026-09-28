# Data model direction

This scaffold intentionally avoids freezing the production schemas before the first vertical slice. The following conceptual objects define the expected boundaries.

| Concept | Purpose |
|---|---|
| EducationalRequest | Normalized user intent and constraints |
| LearningContext | Country/curriculum, subject, track, level, chapter |
| DocumentSpec | Requested artifact type, structure and output constraints |
| Exercise | Statement, solution, concepts, difficulty, provenance |
| SourceReference | Stable source identity/location |
| RetrievedChunk | Retrieval text + score + source metadata |
| AuditIssue | Severity, category, location, explanation, suggested correction |
| Artifact | Generated file metadata and type |

Rules:

- Domain models describe educational meaning, not provider payloads.
- Every externally retrieved fact should be traceable to a `SourceReference` where feasible.
- Audit issues are structured; avoid passing only free-form audit prose between nodes.
- Output paths are metadata, not file contents stored in checkpoint state when avoidable.

## Personal references (implemented)

`Reference` is identified by a SHA-256 content hash-derived ID and records status, source filename/title, size, import time, favorite/enabled flags, parser/chunker fingerprints, embedding model and dimension, index version, OCR use, and chunk count. `ParsedReference` stores `MathBlock` values and the raw converted `source_latex` in its existing JSON cache; `MathChunk` stores presentation content separately from context-enriched embedding text, block type/number, section hierarchy, pages, parent part numbers, and proof/solution relation IDs. `ReferenceSearchResult` distinguishes `EMPTY_LIBRARY`, `NO_RELEVANT_SOURCE`, and `ENOUGH_EVIDENCE` and retains the original query. SQLite is authoritative for these records; HNSW files contain their vector index, linked through SQLite labels. See `docs/rag.md` and migration `0001_reference_library.sql`.

## Chat sessions (implemented)

`ChatSession` records a compact conversational state: id, timestamps, optional project id, turns, current `TaskDraft`, selected source ids, pending questions, produced artifacts and a lightweight plan summary. `ConversationTurn` may carry the parsed intent for the latest message, but prompts and raw model completions are not stored. `TaskDraft` is the mutable bridge from natural language to existing workflow requests: task type, subject, topic, level, duration, outputs, constraints, preferences, source policy, format, curriculum/track and unresolved fields. Once required fields are present and source coverage is acceptable, application code maps the draft to `TDRequest` or `CourseRequest`.
