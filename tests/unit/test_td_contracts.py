"""Offline validation of model and request boundaries."""

import pytest

from hermes_edu.application.use_cases.create_td import parse_audit, parse_draft, parse_plan
from hermes_edu.config.settings import Settings
from hermes_edu.domain.errors import ValidationError
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.request import TDRequest


def test_request_rejects_unsupported_subject_and_count() -> None:
    with pytest.raises(ValidationError):
        TDRequest("Reduction", LearningContext("sample", "MP", "physics"))
    with pytest.raises(ValidationError):
        TDRequest("Reduction", LearningContext("sample", "MP"), exercise_count=0)


def test_model_outputs_require_exact_count_and_provenance() -> None:
    with pytest.raises(ValidationError):
        parse_plan('{"title":"TD","exercises":[]}', 1)
    with pytest.raises(ValidationError):
        parse_draft(
            '{"title":"TD","exercises":[{"title":"A","statement":"B",'
            '"solution":"C","source_ids":["invented"]}]}',
            1,
            {"real"},
        )
    with pytest.raises(ValidationError):
        parse_audit(
            '{"issues":[{"severity":"error","category":"math",'
            '"exercise_index":2,"explanation":"wrong"}]}',
            1,
        )


def test_environment_template_loads() -> None:
    settings = Settings(_env_file=".env.example")  # pyright: ignore[reportCallIssue]
    assert settings.hermes_embedding_provider == "deterministic"
    assert settings.hermes_input_cost_per_million_usd is None
