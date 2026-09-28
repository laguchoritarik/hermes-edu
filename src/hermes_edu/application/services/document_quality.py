"""Deterministic quality gate for generated educational documents."""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from hermes_edu.domain.enums import Severity
from hermes_edu.domain.models.course import CourseDraft, CoursePlan
from hermes_edu.domain.models.quality import (
    CoverageItem,
    CoverageStatus,
    QualityIssue,
    QualityReport,
    QualityStatus,
    SectionCoverage,
)
from hermes_edu.domain.models.source import RetrievedChunk, SourceReference

_INTERNAL_RAG_COMMENT = re.compile(
    r"\b(?:les\s+(?:références|sources|passages)\s+(?:fournies|disponibles|dont\s+nous\s+disposons)"
    r"|le\s+RAG\s+n['\u2019]a\s+pas\s+trouvé"
    r"|nous\s+(?:nous\s+)?(?:limitons|abstenons)"
    r"|sources?\s+insuffisantes?)\b",
    re.IGNORECASE,
)
_LATEX_VISIBLE = re.compile(
    r"(?:\\[A-Za-z]{2,}|[A-Za-z0-9]\_[A-Za-z0-9]|[A-Za-z0-9]\^\{?[A-Za-z0-9])"
)
_MN_K = re.compile(r"M[_\s]*n\s*\(\s*K\s*\)|M_\{?n\}?\s*\(\s*K\s*\)")
_MN_R = re.compile(r"M[_\s]*n\s*\(\s*R\s*\)|M_\{?n\}?\s*\(\s*R\s*\)")
_Z_MULTIPLE_INTERSECTION_ZERO = re.compile(
    r"(?:2\s*Z|2\\mathbb\{Z\}).{0,80}(?:3\s*Z|3\\mathbb\{Z\}).{0,120}"
    r"(?:\{?\s*0\s*\}?|triviale|seulement\s+en\s+0)",
    re.IGNORECASE | re.DOTALL,
)
_PID_BY_INTEGRAL_DOMAIN = re.compile(
    r"\bZ\b.{0,120}(?:principal|principaux|idéaux?).{0,120}(?:intègre|integral\s+domain)",
    re.IGNORECASE | re.DOTALL,
)
_MODULO_CLASS_WITHOUT_BARS = re.compile(
    r"(?:Z\s*/\s*nZ|\\mathbb\{Z\}\s*/\s*n\\mathbb\{Z\}).{0,160}"
    r"(?<!overline\{)a\s*\+\s*(?<!overline\{)b\s*=",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class DocumentQualityGate:
    duplicate_similarity_threshold: float = 0.88

    def evaluate_course(
        self,
        *,
        plan: CoursePlan,
        draft: CourseDraft,
        section_chunks: tuple[tuple[RetrievedChunk, ...], ...],
        sources: tuple[SourceReference, ...],
    ) -> QualityReport:
        coverage = self._coverage(plan, draft, section_chunks)
        source_gaps = tuple(
            QualityIssue(
                "coverage",
                Severity.BLOCKER,
                (
                    f"Section '{section.title}' has insufficient teaching evidence. "
                    "Request an additional reference before generating student-facing content."
                ),
                section_index=index,
            )
            for index, section in enumerate(coverage, start=1)
            if section.evidence_status is not CoverageStatus.COVERED
        )
        content_policy = self._content_policy_issues(draft)
        metadata = self._metadata_contamination(draft, sources)
        duplicates = self._duplicate_issues(draft)
        math = self._math_issues(draft)
        notation = self._notation_issues(draft)
        latex = self._latex_issues(draft)
        all_issues = (
            *source_gaps,
            *content_policy,
            *metadata,
            *duplicates,
            *math,
            *notation,
            *latex,
        )
        blockers = tuple(issue for issue in all_issues if issue.severity is Severity.BLOCKER)
        warnings = tuple(issue for issue in all_issues if issue.severity is Severity.WARNING)
        status = QualityStatus.PASS if not blockers else QualityStatus.DRAFT
        return QualityReport(
            status=status,
            coverage=coverage,
            source_gaps=source_gaps,
            math_issues=math,
            notation_issues=notation,
            duplicates=duplicates,
            latex_issues=latex,
            metadata_contamination=metadata,
            content_policy_issues=content_policy,
            blockers=blockers,
            warnings=warnings,
        )

    def _coverage(
        self,
        plan: CoursePlan,
        draft: CourseDraft,
        section_chunks: tuple[tuple[RetrievedChunk, ...], ...],
    ) -> tuple[SectionCoverage, ...]:
        coverage: list[SectionCoverage] = []
        for index, planned in enumerate(plan.sections):
            chunks = section_chunks[index] if index < len(section_chunks) else ()
            generated = draft.sections[index] if index < len(draft.sections) else None
            required = _required_topics(planned.title, planned.objective)
            support_ids = tuple(chunk.source.source_id for chunk in chunks)
            chunk_ids = tuple(chunk.chunk_id for chunk in chunks)
            has_content = generated is not None and bool(generated.blocks)
            has_evidence = bool(chunks)
            status = (
                CoverageStatus.COVERED if has_content and has_evidence else CoverageStatus.MISSING
            )
            confidence = min(1.0, len(chunks) / 3) if has_content else 0.0
            items = tuple(
                CoverageItem(
                    concept=topic,
                    mandatory=True,
                    supporting_source_ids=support_ids,
                    supporting_chunk_ids=chunk_ids,
                    confidence=confidence,
                    status=status,
                )
                for topic in required
            )
            coverage.append(
                SectionCoverage(
                    section_id=f"section-{index + 1}",
                    title=planned.title,
                    required_topics=required,
                    evidence_status=status,
                    evidence_score=confidence,
                    items=items,
                )
            )
        return tuple(coverage)

    def _content_policy_issues(self, draft: CourseDraft) -> tuple[QualityIssue, ...]:
        issues: list[QualityIssue] = []
        for section_index, block_index, text in _iter_block_text(draft):
            if _INTERNAL_RAG_COMMENT.search(text):
                issues.append(
                    QualityIssue(
                        "content_policy",
                        Severity.BLOCKER,
                        "Internal retrieval/source-gap commentary must not appear in student content.",
                        section_index,
                        block_index,
                    )
                )
        return tuple(issues)

    def _metadata_contamination(
        self, draft: CourseDraft, sources: tuple[SourceReference, ...]
    ) -> tuple[QualityIssue, ...]:
        suspicious = tuple(
            token
            for source in sources
            for token in _metadata_tokens(f"{source.title} {source.location}")
        )
        if not suspicious:
            return ()
        issues: list[QualityIssue] = []
        for section_index, block_index, text in _iter_block_text(draft):
            folded = _fold(text)
            leaked = tuple(token for token in suspicious if token in folded)
            if leaked:
                issues.append(
                    QualityIssue(
                        "metadata_contamination",
                        Severity.BLOCKER,
                        "Source metadata appears in student-facing content.",
                        section_index,
                        block_index,
                    )
                )
        return tuple(issues)

    def _duplicate_issues(self, draft: CourseDraft) -> tuple[QualityIssue, ...]:
        seen: dict[tuple[str, str], tuple[int, int]] = {}
        by_kind: dict[str, list[tuple[int, int, set[str]]]] = defaultdict(list)
        issues: list[QualityIssue] = []
        for section_index, section in enumerate(draft.sections, start=1):
            for block_index, block in enumerate(section.blocks, start=1):
                normalized = _normalize_block(block.text)
                exact_key = (block.kind, normalized)
                if exact_key in seen:
                    issues.append(
                        QualityIssue(
                            "duplicates",
                            Severity.BLOCKER,
                            "Duplicate pedagogical block detected; merge or remove the repeated content.",
                            section_index,
                            block_index,
                            block.source_ids,
                        )
                    )
                    continue
                seen[exact_key] = (section_index, block_index)
                tokens = set(normalized.split())
                for _previous_section, _previous_block, previous_tokens in by_kind[block.kind]:
                    if _jaccard(tokens, previous_tokens) >= self.duplicate_similarity_threshold:
                        issues.append(
                            QualityIssue(
                                "duplicates",
                                Severity.WARNING,
                                "Highly similar block detected; verify that this is a needed reminder, not repetition.",
                                section_index,
                                block_index,
                                block.source_ids,
                            )
                        )
                        break
                by_kind[block.kind].append((section_index, block_index, tokens))
        return tuple(issues)

    def _math_issues(self, draft: CourseDraft) -> tuple[QualityIssue, ...]:
        issues: list[QualityIssue] = []
        for section_index, block_index, text in _iter_block_text(draft):
            compact = text.replace("$", "")
            if _Z_MULTIPLE_INTERSECTION_ZERO.search(compact):
                issues.append(
                    QualityIssue(
                        "math",
                        Severity.BLOCKER,
                        "Suspicious subgroup intersection: multiples of 2 and 3 should be checked against lcm-based reasoning.",
                        section_index,
                        block_index,
                    )
                )
            if _PID_BY_INTEGRAL_DOMAIN.search(compact):
                issues.append(
                    QualityIssue(
                        "math",
                        Severity.BLOCKER,
                        "The principality of ideals must not be justified merely by integrality.",
                        section_index,
                        block_index,
                    )
                )
        return tuple(issues)

    def _notation_issues(self, draft: CourseDraft) -> tuple[QualityIssue, ...]:
        issues: list[QualityIssue] = []
        for section_index, section in enumerate(draft.sections, start=1):
            for block_index, block in enumerate(section.blocks, start=1):
                text = block.text
                if block.kind == "solution" and _MN_R.search(text):
                    previous_statement = " ".join(
                        previous.text for previous in section.blocks[: block_index - 1]
                    )
                    if _MN_K.search(previous_statement):
                        issues.append(
                            QualityIssue(
                                "notation",
                                Severity.BLOCKER,
                                "Statement uses M_n(K) but the solution switches to M_n(R).",
                                section_index,
                                block_index,
                                block.source_ids,
                            )
                        )
                if _MODULO_CLASS_WITHOUT_BARS.search(text.replace("$", "")):
                    issues.append(
                        QualityIssue(
                            "notation",
                            Severity.WARNING,
                            "Modulo-class notation may have lost bars; prefer explicit overline notation.",
                            section_index,
                            block_index,
                            block.source_ids,
                        )
                    )
        return tuple(issues)

    def _latex_issues(self, draft: CourseDraft) -> tuple[QualityIssue, ...]:
        issues: list[QualityIssue] = []
        for section_index, block_index, text in _iter_block_text(draft):
            for prose in _prose_spans(text):
                if _LATEX_VISIBLE.search(prose):
                    issues.append(
                        QualityIssue(
                            "latex",
                            Severity.BLOCKER,
                            "Mathematical notation appears outside math delimiters and would render as raw text.",
                            section_index,
                            block_index,
                        )
                    )
                    break
        return tuple(issues)


def _required_topics(title: str, objective: str) -> tuple[str, ...]:
    tokens = (
        raw.strip()
        for raw in re.split(r"[,;:/]| et | ou ", f"{title} {objective}", flags=re.IGNORECASE)
    )
    return tuple(dict.fromkeys(token for token in tokens if token))


def _iter_block_text(draft: CourseDraft) -> tuple[tuple[int, int, str], ...]:
    return tuple(
        (section_index, block_index, block.text)
        for section_index, section in enumerate(draft.sections, start=1)
        for block_index, block in enumerate(section.blocks, start=1)
    )


def _normalize_block(text: str) -> str:
    return re.sub(r"\s+", " ", _fold(text)).strip()


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return ascii_text.casefold()


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _metadata_tokens(text: str) -> tuple[str, ...]:
    folded = _fold(text)
    tokens: list[str] = []
    for marker in ("lycee", "lycée", "tanger", "professeur", "tarik laguchori"):
        folded_marker = _fold(marker)
        if folded_marker in folded:
            tokens.append(folded_marker)
    return tuple(dict.fromkeys(tokens))


def _prose_spans(text: str) -> tuple[str, ...]:
    spans: list[str] = []
    position = 0
    while position < len(text):
        delimiter_at = text.find("$", position)
        if delimiter_at == -1:
            spans.append(text[position:])
            break
        spans.append(text[position:delimiter_at])
        delimiter = "$$" if text.startswith("$$", delimiter_at) else "$"
        content_end = text.find(delimiter, delimiter_at + len(delimiter))
        if content_end == -1:
            break
        position = content_end + len(delimiter)
    return tuple(spans)
