"""Closed-list wording policy and math-protected text spans for course adaptation."""

from dataclasses import dataclass
from unicodedata import category

from hermes_edu.domain.errors import ValidationError

MAX_WORDING_PHRASES = 200
MAX_WORDING_CHARACTERS = 20_000
_FORBIDDEN_PHRASE_CHARACTERS = frozenset("$\\{}^_=<>+*/")


@dataclass(frozen=True, slots=True)
class CourseWordingPolicy:
    """A closed, non-mathematical list of approved French transition phrases."""

    phrases: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.phrases or len(self.phrases) > MAX_WORDING_PHRASES:
            raise ValidationError(f"Wording policy needs 1-{MAX_WORDING_PHRASES} phrases")
        if len(set(self.phrases)) != len(self.phrases):
            raise ValidationError("Wording policy phrases must be unique")
        if sum(len(phrase) for phrase in self.phrases) > MAX_WORDING_CHARACTERS:
            raise ValidationError("Wording policy exceeds its character budget")
        for phrase in self.phrases:
            if not phrase.strip() or phrase != phrase.strip():
                raise ValidationError("Wording policy phrases must be non-empty and trimmed")
            if _contains_math_or_tex_syntax(phrase):
                raise ValidationError("Wording policy phrases cannot contain math or TeX syntax")


@dataclass(frozen=True, slots=True)
class TextSpan:
    """A half-open character range in a course block."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValidationError("Text spans must be non-empty ordered ranges")


def protected_math_spans(text: str) -> tuple[TextSpan, ...]:
    """Find `$...$` and `$$...$$` spans without interpreting their TeX contents."""
    spans: list[TextSpan] = []
    position = 0
    while position < len(text):
        start = text.find("$", position)
        if start < 0:
            break
        delimiter = "$$" if text.startswith("$$", start) else "$"
        end = text.find(delimiter, start + len(delimiter))
        if end < 0:
            # A malformed delimiter is protected through the end rather than risk rewriting TeX.
            spans.append(TextSpan(start, len(text)))
            break
        end += len(delimiter)
        spans.append(TextSpan(start, end))
        position = end
    return tuple(spans)


def is_prose_span(text: str, span: TextSpan) -> bool:
    """Return whether ``span`` is wholly outside every protected mathematical span."""
    if span.end > len(text):
        return False
    return all(
        span.end <= protected.start or span.start >= protected.end
        for protected in protected_math_spans(text)
    )


def contains_math_or_tex_syntax(text: str) -> bool:
    """Expose the closed-list syntax rule to the application boundary."""
    return _contains_math_or_tex_syntax(text)


def _contains_math_or_tex_syntax(text: str) -> bool:
    for index, character in enumerate(text):
        if character.isdigit() or character in _FORBIDDEN_PHRASE_CHARACTERS:
            return True
        if category(character) == "Sm":
            return True
        if character == "-" and not (
            0 < index < len(text) - 1 and text[index - 1].isalpha() and text[index + 1].isalpha()
        ):
            return True
    return False
