# LLM provider architecture

Initial adapters are planned for DeepSeek, DeepInfra, and OpenRouter.

The application sees a common port rather than provider SDKs. Provider adapters own:

- base URLs/authentication;
- provider request/response mapping;
- model IDs;
- structured-output/tool-call quirks;
- token/cost metadata when available;
- retryable error classification.

A later provider router may choose a model based on task, capability, cost, latency, availability, or fallback policy.

LangChain remains optional. It may be introduced only inside suitable adapter infrastructure if it reduces code without weakening boundaries.

## Model roles

The configuration names roles rather than accounts. `helper` is the economical conversational model controlled by `HERMES_HELPER_PROVIDER` and `HERMES_HELPER_MODEL`; it updates `TaskDraft`, selects compact tool subsets and asks clarifying questions. `generator` is the main planning/generation path (`HERMES_DEFAULT_PROVIDER`, `HERMES_DEFAULT_MODEL`, optional `HERMES_GENERATION_MODEL`). `validator_fast` is ordinary structured verification using the default/generation route, including `verify` fallback inheritance. `validator_strong` is the mathematical audit/revision path configured with `HERMES_AUDIT_PROVIDER`, `HERMES_AUDIT_MODEL`, `HERMES_REVISION_PROVIDER` and `HERMES_REVISION_MODEL`.

These settings contain only provider names, model IDs, limits and environment-variable names. API keys remain in ignored local `.env` files and are never committed.

`helper` currently accepts `deepseek`, `deepinfra` or `openrouter`. If
`HERMES_HELPER_MODEL` is empty, Hermes uses the selected provider's existing
default model setting. This permits a DeepSeek Flash-style fast model, or any
compatible provider model, without hardcoding a vendor/model in application or
domain logic. Helper calls are accounted as task `helper`; their prompt contains
the latest message, `TaskDraft`, session summary, recent compact observations,
selected tool schemas and selected skill cards, not the whole raw transcript.

## v0.1 implementation

DeepSeek is the primary live generation adapter. It requests JSON, retries transient transport failures at most three times, retries an empty JSON response once, and records token usage, latency and price-based cost for each returned call. A dated Flash price snapshot is used when prices are not configured; each record labels its basis. A response truncated by `HERMES_MAX_OUTPUT_TOKENS` fails with an actionable error. `HERMES_GENERATION_MODEL` and `HERMES_AUDIT_MODEL` allow task-specific model selection; `HERMES_*_REASONING_EFFORT` adjusts the [documented DeepSeek effort control](https://api-docs.deepseek.com/api/create-chat-completion/). The default model handles planning. DeepInfra and OpenRouter are available for text-only chat; DeepInfra is also available for embeddings.

## Economical course review routing

`HERMES_AUDIT_PROVIDER` and `HERMES_REVISION_PROVIDER` optionally select `deepinfra` or `openrouter`; their model IDs are `HERMES_AUDIT_MODEL` and `HERMES_REVISION_MODEL` (falling back to `DEEPINFRA_MODEL` or `OPENROUTER_MODEL` for the selected provider). The example configuration uses [Qwen3-235B-A22B-Instruct-2507](https://deepinfra.com/Qwen/Qwen3-235B-A22B-Instruct-2507) as audit primary and [Qwen3-Next-80B-A3B-Instruct](https://deepinfra.com/Qwen/Qwen3-Next-80B-A3B-Instruct) as revision primary. The [Qwen model card](https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507) recommends 16,384 output tokens; Hermes keeps `HERMES_MAX_OUTPUT_TOKENS=16000`. Qwen3.5-35B-A3B remains an optional multimodal-capable model, not a configured preferred candidate. Hermes's `LLMPort` sends text-only JSON requests. These are recommendations, not Hermes API caps.

Each task can configure an ordered CSV of at most four distinct alternatives, excluding its preferred model: `HERMES_AUDIT_FALLBACK_MODELS`, `HERMES_REVISION_FALLBACK_MODELS`, `HERMES_PLAN_FALLBACK_MODELS`, and `HERMES_GENERATION_FALLBACK_MODELS`. `verify` inherits generation alternatives. Entries are `deepseek`, `openrouter:MODEL_ID`, or `deepinfra:MODEL_ID`; a bare model ID is treated as DeepInfra for backward compatibility. Invalid structured output, timeout and provider failure advance once through this list; `candidate_offset` rotates the initial candidate modulo the list length for successive revisions. With fallbacks, every DeepSeek, DeepInfra or OpenRouter candidate gets one 60-second transport attempt and one empty-response attempt. Provider/model usage and cost remain visible per attempt. The local `SQLiteModelOutcomeStore` stores only task, provider/model, outcome, timeout, latency and token/cost aggregates in `.local/llm-metrics.db`; its `summary()` API supports manual latency/validation decisions and never changes routing. Aggregate cost is unknown when any call has unknown cost. PDF conversion remains the iLoveMyLaTeX adapter; DeepInfra is used for `Qwen/Qwen3-Embedding-8B` embeddings when configured.
