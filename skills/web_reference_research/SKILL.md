# web_reference_research

Use this skill when a user asks Hermes to find an educational reference on the Web and optionally add it to the personal reference library.

## Goal

Find a pedagogically relevant source, prefer institutional or authoritative domains when appropriate, inspect it with the `browser` tool, download a PDF only when it is the requested or best source, then hand the downloaded artifact to the existing reference ingestion pipeline.

## Workflow

1. Clarify the topic, level, curriculum, language and maximum number of references if they are missing.
2. Use `browser.open` or `browser.navigate` for search/result pages.
3. Use `browser.read(mode="elements")` and `browser.read(mode="visible")` to inspect compact observations.
4. Prefer sources with stable provenance: official ministries, universities, teacher course pages, institutional PDFs, journals, or well maintained open educational resources.
5. Use returned element IDs such as `e12` for `browser.click`, `browser.fill`, `browser.select`, and `browser.download`.
6. Do not ingest many documents automatically. Keep the count bounded by the user's request.
7. For PDFs, use `browser.download`, validate that the artifact is a PDF, then call the reference ingestion handoff exposed by the browser workflow.
8. Preserve provenance in the response: source URL, page title, domain, retrieval date, filename, content hash and MIME type when available.
9. Summarize actions taken and explain why the selected references are suitable.

## Safety

Do not submit forms, publish, buy, register, upload public files, accept contracts, delete data, or modify accounts without explicit confirmation. Never include passwords, cookies or session secrets in summaries or prompts.
