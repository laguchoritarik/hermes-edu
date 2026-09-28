"""Deterministic local embeddings for offline operation and tests."""

import hashlib
import math
import re

from hermes_edu.application.ports.embeddings import EmbeddingPort


class DeterministicEmbedding(EmbeddingPort):
    """Feature hashing over terms; useful for small offline indexes, not semantic reasoning."""

    @property
    def model_id(self) -> str:
        return "feature-hash-v1-256"

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            vector = [0.0] * 256
            for term in re.findall(r"\w+", text.lower()):
                index = (
                    int.from_bytes(hashlib.blake2b(term.encode(), digest_size=2).digest(), "big")
                    % 256
                )
                vector[index] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append(tuple(value / norm for value in vector))
        return tuple(vectors)
