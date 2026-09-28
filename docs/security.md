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
- browser automation uses compact DOM/accessibility observations, redacts
  sensitive fields in snapshots/traces, supports allow/deny domain
  configuration, and requires confirmation for consequential actions.
- Helper Agent decisions are structured and validated before execution. The LLM
  can request `UPDATE_STATE`, tool calls or delegation, but code enforces
  `ToolRegistry` allowlists, filesystem roots, browser confirmations,
  `HERMES_AGENT_MAX_STEPS`, reference policies and quality gates.
- Tool observations sent back to the helper are compact summaries with stable
  IDs, not raw HTML, full documents, logs or unrestricted filesystem listings.

## Privacy

Public fixtures must be synthetic or explicitly distributable. Real student/user documents must not be committed to Git.

## v0.1 concrete controls

Local ingestion confines files to the configured data directory, limits file size, and bounds PDF pages. Model-authored content is validated JSON, then escaped into a trusted TeX template. The compiler revalidates the source hash and runs with a fixed argument list, no shell escape, a timeout and workspace confinement. MCP compilation takes only a constrained thread ID and honors `HERMES_MCP_ALLOWED_ROOTS`. CLI checkpoint creation requires strict msgpack deserialization.
