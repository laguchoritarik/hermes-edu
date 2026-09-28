# RAG architecture

## Ingestion

Source → parser → normalized document → chunks → embeddings → store/index.

## Retrieval

Query → embedding → candidate retrieval → optional metadata filters/reranking → Top-k chunks with provenance.

## Design requirements

- retrieval port independent of SQLite/vector backend;
- every chunk keeps source identity/location;
- embedding model/version recorded;
- chunking policy versioned;
- index rebuild supported;
- do not expose whole document libraries to the LLM when Top-k context is sufficient;
- retrieved text is data, not trusted executable instruction.

SQLite + sqlite-vec is the first local option, not a permanent architectural dependency.

## Personal PDF references

The existing TD knowledge path above remains available. Personal PDF references use `ReferenceLibrary` through application ports. Import reads an allowlisted PDF under `HERMES_DATA_DIR`, hashes its bytes with SHA-256, retains the original under `.local/reference-files`, converts the PDF with iLoveMyLaTeX, persists the returned LaTeX in the parsed cache, and structures it before chunking. The default `HERMES_REFERENCE_PDF_MODE=latex` applies to text PDFs and scans alike; explicit `text` mode supports offline extraction. Failed conversions never silently fall back to local text. `MathSemanticChunker` makes one chunk per definition, theorem, proof, example, exercise, solution, etc.; only oversized blocks are divided at logical boundaries. Proofs and solutions retain their relation to their source block, and `related_chunks` retrieves that content only on request. Each chunk stores its original content and a separate context-enriched embedding text, plus document, section and page provenance. When converted LaTeX has no page mapping, chunks carry the complete document page range rather than an invented exact location.

SQLite is authoritative for documents, statuses, parser/chunker fingerprints, parsed documents, chunks, model/dimension/index metadata, and HNSW label mappings. Native hnswlib files store vectors with a persistent cosine HNSW index. A document reaches `READY` only after SQLite chunks and all vectors are present and verified. The content hash deduplicates renamed PDFs. A matching pipeline fingerprint skips all stages; a chunker change reuses the parsed cache; a model change reuses parsed/chunk caches and computes new embeddings. Failed batches retain completed stage artifacts for retry. Explicit reindex forces the pipeline. Old TD `SQLiteKnowledgeStore` tables remain untouched.

The registry also records the embedding provider. Provider changes scope a new HNSW index; `HERMES_REFERENCE_EMBEDDING_DIMENSION` can enforce the returned width (0 detects it automatically).

Chunk soft/hard limits use a conservative model-independent token estimate; they are safeguards for unusually long blocks, not primary segmentation boundaries.

Search embeds only the query, filters eligible labels by metadata, performs HNSW ANN, then applies a configurable cosine relevance threshold. Hermes asks HNSW for a slightly larger candidate pool, then applies deterministic semantic deduplication/diversification so repeated or near-identical chunks do not consume the final `top_k` when distinct evidence is available. The structured reference log records the semantic query, requested and candidate top-k sizes, candidate count, retained count and eliminated duplicate chunk IDs as an internal retrieval trace. The outcome is `EMPTY_LIBRARY`, `NO_RELEVANT_SOURCE`, or `ENOUGH_EVIDENCE`; the original query is returned so a caller can add a missing PDF and repeat it. `top_k` is per call, defaults to 5 and is capped at 30 by settings. `purpose=exercises` excludes solutions; linked solutions can then be fetched explicitly. HNSW candidate count is an upper bound, not a mandate to send every hit to an LLM. Calibrate `HERMES_REFERENCE_MIN_SCORE` for the chosen embedding model on a representative corpus; 0.35 is an initial default.

The chat interface uses the same `ReferenceLibrary.search()` result before a ready draft is run. `ENOUGH_EVIDENCE` selects compact source IDs for the session; `EMPTY_LIBRARY` and `NO_RELEVANT_SOURCE` become pending chat questions asking the user to add a PDF or adjust the request. These diagnostics remain workflow state and never become prose in the generated course, TD or correction.

## Browser-acquired references

The Browser Tool stores downloads under `.hermes/browser/sessions/...` and never
executes them. When a downloaded PDF is added to the library, Hermes reads its
bytes and calls `ReferenceLibrary.import_pdf_bytes`; deduplication, parsing,
chunking, embeddings and HNSW indexing remain the same pipeline as local
`references add`.

## v0.1 implementation

`SQLiteKnowledgeStore` keeps versioned source/chunk metadata and JSON vectors. It scans only chunks matching curriculum, track, subject, kind and embedding model, then returns top-k cosine matches. Unchanged chunks are not re-embedded. The default feature-hash embedding supports offline small-corpus operation; DeepInfra embeddings are optional. sqlite-vec acceleration is deferred (ADR 0011).
