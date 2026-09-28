"""DeepInfra OpenAI-compatible embedding adapter."""

from openai import OpenAI

from hermes_edu.application.ports.embeddings import EmbeddingPort
from hermes_edu.domain.errors import GenerationError


class DeepInfraEmbedding(EmbeddingPort):
    def __init__(
        self, *, api_key: str, base_url: str, model: str, client: OpenAI | None = None
    ) -> None:
        if not model or (not api_key and client is None):
            raise GenerationError("DeepInfra embedding model and API key are required")
        self._client = client or OpenAI(
            api_key=api_key, base_url=base_url, max_retries=2, timeout=60.0
        )
        self._model = model

    @property
    def model_id(self) -> str:
        return self._model

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        try:
            response = self._client.embeddings.create(model=self._model, input=list(texts))
        except Exception as exc:
            raise GenerationError(f"Embedding request failed: {type(exc).__name__}") from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        return tuple(tuple(item.embedding) for item in ordered)
