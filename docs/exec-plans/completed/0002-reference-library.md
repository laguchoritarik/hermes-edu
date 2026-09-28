# Reference library implementation plan

Status: completed on 2026-09-27. All four delivery phases were implemented and validated.

## Existing boundaries

Keep the TD source/chunk tables and `SQLiteVectorRetriever` intact. Reuse `EmbeddingPort`,
DeepInfra, PyMuPDF, Settings, Typer, MCP v2, and the composition root. Add the reference
library as application use cases with repository, parser, file, and vector ports.

## Delivery phases

1. Add domain records, semantic PDF parsing/chunking, and version fingerprints. Cover
   mathematical block boundaries and relations with offline tests.
2. Add a migration of the existing SQLite knowledge database, durable parsed/chunk caches,
   content hash deduplication, and a separate persistent HNSW vector index. Test duplicate,
   rename, invalidation, failure, deletion, and restart paths.
3. Add bounded semantic search, relevance outcomes, preferred/disabled scopes, batch/directory
   import, explicit reindex, then thin CLI/MCP delivery. Test the user workflow offline.
4. Update the existing specification, README, architecture, RAG, MCP, configuration, roadmap,
   manifest, and ADRs. Run lint, typecheck, tests, build, and dependency audit.

## Invariants

`READY` means persisted chunks, embeddings, HNSW index, and SQLite registry agree. The same
PDF bytes retain one document ID across filenames and paths. An interrupted or failed import
never claims `READY`; completed stage artifacts can be reused. Existing TD data and APIs
remain available. Test documents are synthetic and no real keys enter the repository.

## Validation

The full shared repository passed `make lint`, `make typecheck`, `make test` (51 tests), and `make build`. `make audit` reported no known vulnerabilities. A live DeepInfra Qwen3 embedding call returned one 4096-dimensional vector and a DeepSeek smoke call succeeded. The iLoveMyLaTeX multipart contract passes under a mocked HTTP client; live uploads of synthetic PDFs were rejected by the external service or hit a transport error, as recorded in `docs/operations-v01.md`.
