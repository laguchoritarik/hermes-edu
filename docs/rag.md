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
