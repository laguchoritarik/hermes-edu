CREATE TABLE IF NOT EXISTS reference_documents (
    document_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    title TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    imported_at TEXT NOT NULL,
    status TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    preferred INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL,
    error TEXT NOT NULL,
    parser_fingerprint TEXT NOT NULL,
    chunker_fingerprint TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_provider TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    index_version TEXT NOT NULL,
    ocr_used INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_parsed (
    document_id TEXT NOT NULL REFERENCES reference_documents(document_id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (document_id, fingerprint)
);
CREATE TABLE IF NOT EXISTS reference_chunks (
    chunk_id TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES reference_documents(document_id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    block_type TEXT NOT NULL,
    chapter TEXT NOT NULL,
    section TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (chunk_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS reference_chunks_document ON reference_chunks(document_id, fingerprint);
CREATE TABLE IF NOT EXISTS reference_vector_labels (
    label INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL,
    model TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    index_version TEXT NOT NULL,
    indexed INTEGER NOT NULL DEFAULT 0,
    UNIQUE (chunk_id, model, dimension, index_version)
);
CREATE INDEX IF NOT EXISTS reference_vectors_chunk ON reference_vector_labels(chunk_id);
PRAGMA user_version = 1;
