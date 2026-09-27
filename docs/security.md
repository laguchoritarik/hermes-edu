# Security architecture

## Threat surfaces

1. Prompt injection in retrieved documents.
2. Model-generated tool names/arguments.
3. Path traversal / filesystem access.
4. LaTeX command execution.
5. Checkpoint deserialization.
6. Leaked API keys or educational/private data.
7. Malicious/oversized PDFs during ingestion.
8. Dependency supply-chain vulnerabilities.

## Controls

- Model outputs are untrusted until validated.
- MCP tool allowlist + typed argument validation.
- Resource/file access resolves under configured roots.
- `LANGGRAPH_STRICT_MSGPACK=true` for new checkpoint databases.
- Separate checkpoint database from RAG/application databases.
- LaTeX invocation uses fixed executable and options, disabled unrestricted shell escape, timeout, workspace confinement.
- API keys read from environment only and redacted from logs.
- ingestion limits file type/size and records provenance.
- dependency audit in CI.
- human approval before configured high-impact actions.

## Privacy

Public fixtures must be synthetic or explicitly distributable. Real student/user documents must not be committed to Git.
