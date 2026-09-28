# MCP architecture

Hermes targets MCP Python SDK v2.

## Tools
Actions. The model may request them, but Hermes validates tool identity/arguments and controls execution.

## Resources
Data exposed by URI. Listing metadata should remain cheap; large content is read only when needed.

## Prompts
Reusable MCP message/workflow templates. They do not replace application/domain logic.

## Boundary rule

MCP server functions should be thin adapters over application services. Hermes core must remain callable directly without MCP.

Potential future Hermes MCP surface:

- resources: curricula, course references, templates;
- tools: knowledge search, chat/session handling, LaTeX compile/validate, controlled document operations;
- prompts: create course/TD/DM/DS, explain, correct.

The reusable conversation surface is `ChatService`: start/resume session, handle message, inspect status/plan/sources, add a reference, run or cancel. A future MCP chat tool must call that service through application ports, exactly like the terminal adapter, so MCP cannot bypass coverage, quality gate, LaTeX validation or publication rules. The Helper Agent and `ToolRouter` live behind this same service; MCP must not expose a second agent loop with broader tools or raw provider clients.

## v0.1 MCP v2 surface

`hermes-edu-mcp` uses `MCPServer` over stdio. It exposes a synthetic curriculum resource, a versioned TD template resource, a `create_td` prompt, and `search_knowledge`, `validate_td_latex`, and `compile_td_latex` tools. Search delegates to the local retriever and compiler operations delegate to the document adapter. Compilation accepts a thread ID, never an arbitrary file path, and requires the workspace MCP allowlist entry.

## Personal references

`add_reference(path, title)`, `add_references(paths)`, and `import_reference_directory(directory)` accept PDFs only under `HERMES_DATA_DIR`. `list_references`, `get_reference(document_id)`, `set_reference_enabled`, `set_reference_preferred`, `remove_reference`, and `reindex_reference` delegate to the application use case. `search_references(query, top_k, document_ids, block_types, chapter, section, preferred_only, purpose)` returns `outcome`, the original `query`, and bounded `hits`. Each hit includes chunk/document IDs, block type/number, chapter/section, pages, content, relation IDs, document title and semantic score; the internal embedding text is omitted. `purpose` accepts `definition`, `theorem`, `proof`, `example`, `exercises`, or `solutions`; `get_related_reference_chunks(chunk_id)` fetches a linked proof/statement or exercise/solution when needed.

Example: `search_references(query="bases vectorielles", top_k=3, purpose="theorem")`. `EMPTY_LIBRARY` means no active references; `NO_RELEVANT_SOURCE` means the active library has no sufficiently relevant result in the requested scope. In either case the caller may offer to add a PDF and repeat the returned query. Invalid paths, IDs, scopes or top_k are surfaced as tool errors. MCP handlers contain no parsing, chunking, or vector search logic.

Reference queries accept 1–4 000 characters, including a bounded official programme subpart when used by the course workflow. Leave `purpose` empty to search all block types. New PDF imports use the configured iLoveMyLaTeX conversion before semantic chunking; a cached, fully processed reference requires no new conversion.

## Browser tools

The MCP server exposes the same browser service as CLI/chat with tools such as
`browser_open`, `browser_read`, `browser_click`, `browser_fill`,
`browser_scroll`, `browser_download`, and `browser_screenshot`. These handlers
are thin adapters: they do not import Playwright directly and they return compact
observations rather than raw HTML. `browser_download(add_reference=true)` imports
the captured PDF bytes through the existing reference library pipeline.

## Quality reports

Course workflow results include quality report artifacts when invoked through CLI or any future MCP-facing course wrapper: `quality_report.json` is machine-readable and `quality_report.md` is human-readable. Source gaps, blockers and metadata contamination remain workflow data; MCP adapters must not copy those diagnostics into student-facing document content.
