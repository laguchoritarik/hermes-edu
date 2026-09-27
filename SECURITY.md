# Security Policy

## Reporting

Please do not open a public issue for a vulnerability involving credentials, arbitrary code execution, path traversal, checkpoint deserialization, or private educational data. Use GitHub's private security advisory mechanism when available.

## Security baseline

- Never commit `.env` or credentials.
- Keep `LANGGRAPH_STRICT_MSGPACK=true` for checkpoint deserialization.
- Treat LLM output as untrusted input.
- Validate tool names and arguments before MCP execution.
- Restrict filesystem access to configured roots.
- Do not execute generated LaTeX with unrestricted shell escape.
- Keep student/user documents out of the public repository.
- Run dependency audit in CI.

See `docs/security.md` for the architecture-level threat model.
