"""Closed-list transition wording keeps course mathematics and structure immutable."""

import json

import pytest

from hermes_edu.application.ports.llm import ModelRequest, ModelResponse, ModelUsage
from hermes_edu.application.use_cases.adapt_course_wording import AdaptCourseWording
from hermes_edu.domain.errors import GenerationError, ValidationError
from hermes_edu.domain.models.course import CourseBlock, CourseSection
from hermes_edu.domain.models.course_wording import CourseWordingPolicy


class ScriptedLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.tasks: list[str] = []

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        self.tasks.append(request.task)
        return ModelResponse(self.responses.pop(0), ModelUsage("fake", "fixed", 1, 1, 0, 1, 0.0))


def _section(text: str) -> CourseSection:
    return CourseSection("Exemples", (CourseBlock("example", text),), ("source",))


def _edit(start: int, end: int, original: str, phrase_index: int = 0) -> str:
    return json.dumps(
        {
            "status": "apply",
            "edits": [
                {
                    "block_index": 0,
                    "start": start,
                    "end": end,
                    "original": original,
                    "phrase_index": phrase_index,
                    "is_transition": True,
                }
            ],
        }
    )


def test_replaces_only_a_transition_and_preserves_formula_bytes_and_punctuation() -> None:
    text = "Donc, $\\text{si } x\\leq y$, on a $f(x)\\leq f(y)$."
    start = text.index("Donc,")
    llm = ScriptedLLM([_edit(start, start + len("Donc,"), "Donc,")])
    adapter = AdaptCourseWording(llm, max_output_tokens=100)
    adapted = adapter.adapt(_section(text), CourseWordingPolicy(("Par conséquent,",))).value

    assert (
        adapted.blocks[0].text == "Par conséquent, $\\text{si } x\\leq y$, on a $f(x)\\leq f(y)$."
    )
    assert llm.tasks == ["wording"]


def test_transition_replacement_starts_a_new_paragraph_inside_examples() -> None:
    text = "On majore d'abord la fonction. Donc, $x\\leq y$, la conclusion suit."
    start = text.index("Donc,")
    llm = ScriptedLLM([_edit(start, start + len("Donc,"), "Donc,")])
    adapter = AdaptCourseWording(llm, max_output_tokens=100)
    adapted = adapter.adapt(_section(text), CourseWordingPolicy(("Ainsi,",))).value

    assert adapted.blocks[0].text == (
        "On majore d'abord la fonction. \n\nAinsi, $x\\leq y$, la conclusion suit."
    )


def test_wording_verification_allows_transition_length_changes_before_formulas() -> None:
    original = _section("Donc, $a=b$.")
    adapted = _section("Par conséquent, $a=b$.")
    verifier = AdaptCourseWording(
        ScriptedLLM(['{"faithful":true,"reason":"La formule est inchangée."}']),
        max_output_tokens=100,
    )

    assert verifier.verify(original, adapted, CourseWordingPolicy(("Par conséquent,",))).value


def test_rejects_unknown_indices_missing_edits_and_formula_or_operator_ranges() -> None:
    text = "Donc $x\\leq y$."
    start = text.index("Donc")
    unknown = _edit(start, start + 4, "Donc", phrase_index=4)
    with pytest.raises(GenerationError, match="twice"):
        AdaptCourseWording(ScriptedLLM([unknown, unknown]), max_output_tokens=100).adapt(
            _section(text), CourseWordingPolicy(("Ainsi",))
        )

    missing = json.dumps({"status": "apply", "edits": []})
    with pytest.raises(GenerationError, match="twice"):
        AdaptCourseWording(ScriptedLLM([missing, missing]), max_output_tokens=100).adapt(
            _section(text), CourseWordingPolicy(("Ainsi",))
        )

    formula_start = text.index("x")
    formula = _edit(formula_start, formula_start + 1, "x")
    with pytest.raises(GenerationError, match="twice"):
        AdaptCourseWording(ScriptedLLM([formula, formula]), max_output_tokens=100).adapt(
            _section(text), CourseWordingPolicy(("Ainsi",))
        )


def test_no_change_plain_prose_and_semantic_verification_false_is_returned() -> None:
    original = _section("Cette méthode répond à l'exercice sans formule.")
    adapter = AdaptCourseWording(
        ScriptedLLM(['{"status":"no_change","edits":[]}']), max_output_tokens=100
    )
    assert adapter.adapt(original, CourseWordingPolicy(("Ainsi",))).value == original

    adapted = _section("Cette méthode répond à l'exercice sans formule.")
    verification_llm = ScriptedLLM(['{"faithful":false,"reason":"Le sens a changé."}'])
    verifier = AdaptCourseWording(verification_llm, max_output_tokens=100)
    result = verifier.verify(original, adapted, CourseWordingPolicy(("Ainsi",)))
    assert result.value is False
    assert verification_llm.tasks == ["verify"]


def test_explicit_refusal_stops_adaptation_without_free_text_fallback() -> None:
    refusal = '{"status":"refuse","edits":[]}'
    with pytest.raises(GenerationError, match="twice"):
        AdaptCourseWording(ScriptedLLM([refusal, refusal]), max_output_tokens=100).adapt(
            _section("Donc, la conclusion suit."), CourseWordingPolicy(("Ainsi",))
        )


def test_no_change_is_still_semantically_checked_against_the_closed_list() -> None:
    original = _section("Donc, la conclusion suit.")
    verifier = AdaptCourseWording(
        ScriptedLLM(['{"faithful":false,"reason":"Donc ne figure pas dans la liste."}']),
        max_output_tokens=100,
    )
    assert verifier.verify(original, original, CourseWordingPolicy(("Ainsi",))).value is False


def test_verify_rejects_changed_repeated_formulas_or_noneligible_blocks() -> None:
    original = CourseSection(
        "Exemples",
        (
            CourseBlock("text", "Définition fixe."),
            CourseBlock("solution", "Donc $a=b$ et encore $a=b$."),
        ),
        ("source",),
    )
    changed_math = CourseSection(
        "Exemples",
        (
            CourseBlock("text", "Définition fixe."),
            CourseBlock("solution", "Ainsi $a\\leq b$ et encore $a=b$."),
        ),
        ("source",),
    )
    with pytest.raises(ValidationError, match="mathematical"):
        AdaptCourseWording(ScriptedLLM([]), max_output_tokens=100).verify(
            original, changed_math, CourseWordingPolicy(("Ainsi",))
        )

    changed_text = CourseSection(
        "Exemples",
        (
            CourseBlock("text", "Définition modifiée."),
            CourseBlock("solution", "Ainsi $a=b$ et encore $a=b$."),
        ),
        ("source",),
    )
    with pytest.raises(ValidationError, match="non-example"):
        AdaptCourseWording(ScriptedLLM([]), max_output_tokens=100).verify(
            original, changed_text, CourseWordingPolicy(("Ainsi",))
        )

    changed_block_citation = CourseSection(
        "Exemples",
        (
            CourseBlock("text", "Définition fixe."),
            CourseBlock("solution", "Ainsi $a=b$ et encore $a=b$.", ("other",)),
        ),
        ("source",),
    )
    with pytest.raises(ValidationError, match="citations"):
        AdaptCourseWording(ScriptedLLM([]), max_output_tokens=100).verify(
            original, changed_block_citation, CourseWordingPolicy(("Ainsi",))
        )


def test_policy_rejects_math_syntax_duplicates_and_excess() -> None:
    with pytest.raises(ValidationError):
        CourseWordingPolicy(("Donc $x$",))
    with pytest.raises(ValidationError):
        CourseWordingPolicy(("Ainsi", "Ainsi"))
    with pytest.raises(ValidationError):
        CourseWordingPolicy(tuple(f"Phrase {index}" for index in range(201)))
    with pytest.raises(ValidationError):
        CourseWordingPolicy(("Ainsi ≤",))
    with pytest.raises(ValidationError):
        CourseWordingPolicy(("Donc-",))
    assert CourseWordingPolicy(("C'est-à-dire",)).phrases == ("C'est-à-dire",)
