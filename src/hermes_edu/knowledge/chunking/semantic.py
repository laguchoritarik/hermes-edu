"""Mathematical objects are the primary chunk boundaries."""

import re
from hashlib import sha256

from hermes_edu.domain.models.reference import MathBlock, MathChunk, ParsedReference


def _token_count(text: str) -> int:
    # Conservative model-independent estimate; semantic boundaries are chosen first.
    return max(len(text.split()), (len(text) + 3) // 4)


class MathSemanticChunker:
    """Keep each math object whole unless it exceeds the configured hard limit."""

    version = "math-semantic-v1"

    def __init__(
        self, *, soft_max_tokens: int = 1000, hard_max_tokens: int = 1400, overlap_tokens: int = 0
    ) -> None:
        if not 100 <= soft_max_tokens <= hard_max_tokens or overlap_tokens < 0:
            raise ValueError("Invalid semantic chunk limits")
        self.soft_max_tokens = soft_max_tokens
        self.hard_max_tokens = hard_max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, parsed: ParsedReference, title: str) -> tuple[MathChunk, ...]:
        chunks: list[MathChunk] = []
        for block in parsed.blocks:
            parts = self._split_large_block(block)
            for number, content in enumerate(parts, start=1):
                headings = [
                    f"Document: {title}",
                    *(
                        f"{name}: {value}"
                        for name, value in (
                            ("Chapter", block.chapter),
                            ("Section", block.section),
                            ("Subsection", block.subsection),
                        )
                        if value
                    ),
                    f"Type: {block.block_type}{' ' + block.number if block.number else ''}",
                ]
                embedding_text = "\n".join((*headings, content))
                chunk_id = sha256(
                    f"{parsed.document_id}\x1f{block.block_id}\x1f{self.version}\x1f"
                    f"{self.soft_max_tokens}\x1f{self.hard_max_tokens}\x1f{number}\x1f"
                    f"{embedding_text}".encode()
                ).hexdigest()[:32]
                chunks.append(
                    MathChunk(
                        chunk_id=chunk_id,
                        document_id=parsed.document_id,
                        block_id=block.block_id,
                        block_type=block.block_type,
                        content=content,
                        embedding_text=embedding_text,
                        page_start=block.page_start,
                        page_end=block.page_end,
                        chapter=block.chapter,
                        section=block.section,
                        subsection=block.subsection,
                        number=block.number,
                        title=block.title,
                        parent_id=block.block_id if len(parts) > 1 else "",
                        part_number=number,
                        parts_count=len(parts),
                        relation=block.relation,
                        related_block_id=block.related_block_id,
                    )
                )
        return tuple(chunks)

    def _split_large_block(self, block: MathBlock) -> tuple[str, ...]:
        if _token_count(block.text) <= self.hard_max_tokens:
            return (block.text,)
        paragraphs = [
            part.strip()
            for part in re.split(
                r"\n\s*\n|(?=^\s*(?:Step|Étape|Case|Cas|Question)\s)", block.text, flags=re.M
            )
            if part.strip()
        ]
        if len(paragraphs) == 1:
            paragraphs = [line.strip() for line in block.text.splitlines() if line.strip()]
        if len(paragraphs) == 1:
            paragraphs = [
                part.strip()
                for part in re.split(r"(?<=[.;!?])\s+(?=[A-ZÀ-Ý])", block.text)
                if part.strip()
            ]
        units: list[str] = []
        for paragraph in paragraphs:
            if _token_count(paragraph) <= self.hard_max_tokens:
                units.append(paragraph)
                continue
            words: list[str] = []
            for word in paragraph.split():
                candidate = " ".join((*words, word))
                if words and _token_count(candidate) > self.hard_max_tokens:
                    units.append(" ".join(words))
                    words = []
                words.append(word)
            if words:
                units.append(" ".join(words))
        parts: list[str] = []
        current: list[str] = []
        count = 0
        for unit in units:
            size = _token_count(unit)
            if current and count + size > self.hard_max_tokens:
                parts.append("\n\n".join(current))
                current, count = [], 0
            current.append(unit)
            count += size
            if count >= self.soft_max_tokens:
                parts.append("\n\n".join(current))
                current, count = [], 0
        if current:
            parts.append("\n\n".join(current))
        return tuple(parts)
