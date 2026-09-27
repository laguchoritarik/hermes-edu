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
