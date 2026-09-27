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
