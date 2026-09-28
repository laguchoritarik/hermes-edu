"""Bound retrieval context before it reaches a model call."""

from hermes_edu.domain.models.source import RetrievedChunk


def build_context(chunks: tuple[RetrievedChunk, ...], *, token_budget: int) -> str:
    """Pack complete provenance-bearing chunks within a conservative token estimate."""
    remaining = token_budget * 3  # Three characters per token avoids optimistic packing.
    parts: list[str] = []
    for chunk in chunks:
        label = f"[{chunk.chunk_id}] {chunk.source.title} ({chunk.source.location})\n"
        if len(label) >= remaining:
            break
        text = chunk.text[: remaining - len(label)]
        if not text:
            break
        parts.append(label + text)
        remaining -= len(label) + len(text)
        if len(text) < len(chunk.text):
            break
    return "\n\n".join(parts)
