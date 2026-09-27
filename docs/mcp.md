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
- tools: knowledge search, LaTeX compile/validate, controlled document operations;
- prompts: create course/TD/DM/DS, explain, correct.
