"""Course CLI exercises a real graph/checkpoint/renderer with offline model ports."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_edu.application.ports.llm import ModelRequest, ModelResponse, ModelUsage
from hermes_edu.application.use_cases.adapt_course_wording import AdaptCourseWording
from hermes_edu.application.use_cases.create_course import CreateCourse
from hermes_edu.bootstrap import CourseRuntime
from hermes_edu.config.settings import Settings
from hermes_edu.documents.latex.course import LatexCourseAdapter
from hermes_edu.documents.latex.math_content import validate_math_text
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.reference import (
    MathChunk,
    ReferenceHit,
    ReferenceSearchResult,
    SearchOutcome,
)
from hermes_edu.domain.models.source import RetrievedChunk, SourceReference
from hermes_edu.interfaces.cli import courses
from hermes_edu.interfaces.cli.app import app


class CourseModel:
    def __init__(self) -> None:
        self.tasks: list[str] = []

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        self.tasks.append(request.task)
        if request.task == "plan":
            content = (
                '{"title":"Intégrales MP","sections":[{"title":"Continuité",'
                '"objective":"Appliquer la domination",'
                '"curriculum_source_ids":["official:1"]}]}'
            )
        elif request.task == "generate":
            content = json.dumps(
                {
                    "title": "Continuité",
                    "blocks": [
                        {
                            "kind": "theorem",
                            "text": r"La fonction $F$ est continue.",
                            "source_ids": ["ref:1"],
                        }
                    ],
                    "source_ids": ["ref:1"],
                }
            )
        else:
            content = '{"issues":[]}'
        return ModelResponse(content, ModelUsage("fake", "fixed", 10, 5, 0, 1, 0.0))


class RecoveringCourseModel(CourseModel):
    def __init__(self) -> None:
        super().__init__()
        self.generate_attempts = 0

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        if request.task != "generate":
            return super().complete_json(request)
        self.tasks.append(request.task)
        self.generate_attempts += 1
        if self.generate_attempts <= 2:
            content = json.dumps(
                {
                    "title": "Continuité",
                    "blocks": [
                        {
                            "kind": "theorem",
                            "text": r"La fonction $\input{secret}$ est continue.",
                            "source_ids": ["ref:1"],
                        }
                    ],
                    "source_ids": ["ref:1"],
                }
            )
        else:
            content = json.dumps(
                {
                    "title": "Continuité",
                    "blocks": [
                        {
                            "kind": "theorem",
                            "text": r"La fonction $F$ est continue.",
                            "source_ids": ["ref:1"],
                        }
                    ],
                    "source_ids": ["ref:1"],
                }
            )
        return ModelResponse(content, ModelUsage("fake", "fixed", 10, 5, 0, 1, 0.0))


class Curriculum:
    def retrieve(
        self, query: str, context: LearningContext, *, kind: str, top_k: int
    ) -> tuple[RetrievedChunk, ...]:
        return (
            RetrievedChunk(
                "official:1",
                "Continuité sous domination intégrable.",
                SourceReference(
                    "official", "Programme MP", "https://official.example/mp", "public"
                ),
                1.0,
            ),
        )


class References:
    def search(
        self, query: str, *, top_k: int | None = None, **kwargs: object
    ) -> ReferenceSearchResult:
        return ReferenceSearchResult(
            SearchOutcome.ENOUGH_EVIDENCE,
            (
                ReferenceHit(
                    MathChunk(
                        "ref:1",
                        "ref",
                        "ref:1",
                        "theorem",
                        "Continuité et domination",
                        "Continuité",
                        1,
                        1,
                    ),
                    "Cours MP",
                    1.0,
                ),
            ),
            query,
        )


def test_cli_course_approval_resume_preserves_tex_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = CourseModel()
    settings = Settings(hermes_embedding_provider="deterministic")
    monkeypatch.setattr(courses, "load_settings", lambda: settings)

    def runtime(
        current: Settings, *, tex_only: bool = False, approval_required: bool | None = None
    ) -> CourseRuntime:
        service = CreateCourse(
            llm=model,
            curriculum=Curriculum(),
            references=References(),
            documents=LatexCourseAdapter(tmp_path, compile_pdf=not tex_only, engine="nonexistent"),
            validate_text=validate_math_text,
            top_k=2,
            context_token_budget=500,
            max_output_tokens=500,
        )
        return CourseRuntime(
            service,
            tmp_path / "checkpoints.db",
            approval_required is not False,
            1,
            1,
            AdaptCourseWording(model, max_output_tokens=500),
        )

    monkeypatch.setattr(courses, "build_course_runtime", runtime)
    runner = CliRunner()
    phrase_file = tmp_path / "phrases.txt"
    phrase_file.write_text("Donc\nAinsi\n", encoding="utf-8")
    args = [
        "course",
        "Intégrales",
        "--curriculum",
        "official-mp",
        "--sections",
        "1",
        "--tex-only",
        "--thread-id",
        "course-test",
        "--phrases-file",
        str(phrase_file),
    ]
    paused = runner.invoke(app, args)
    assert paused.exit_code == 0, paused.output
    assert "awaiting approval" in paused.output
    assert model.tasks == ["plan"]
    duplicate = runner.invoke(app, args)
    assert duplicate.exit_code == 1
    refused = runner.invoke(app, ["course-resume", "course-test"])
    assert refused.exit_code == 1 and "awaits plan approval" in refused.output
    phrase_file.unlink()  # The persisted list, not a mutable file, controls resume.
    resumed = runner.invoke(app, ["course-resume", "course-test", "approve"])
    assert resumed.exit_code == 0, resumed.output
    assert (tmp_path / "course-test" / "course.tex").exists()
    assert model.tasks == ["plan", "generate", "audit"]
    completed = runner.invoke(app, ["course-resume", "course-test"])
    assert completed.exit_code == 0
    assert model.tasks == ["plan", "generate", "audit"]
    missing = runner.invoke(app, ["course-resume", "absent"])
    assert missing.exit_code == 1 and "No course checkpoint" in missing.output


def test_cli_course_auto_recover_retries_failed_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = RecoveringCourseModel()
    settings = Settings(hermes_embedding_provider="deterministic")
    monkeypatch.setattr(courses, "load_settings", lambda: settings)

    def runtime(
        current: Settings, *, tex_only: bool = False, approval_required: bool | None = None
    ) -> CourseRuntime:
        service = CreateCourse(
            llm=model,
            curriculum=Curriculum(),
            references=References(),
            documents=LatexCourseAdapter(tmp_path, compile_pdf=not tex_only, engine="nonexistent"),
            validate_text=validate_math_text,
            top_k=2,
            context_token_budget=500,
            max_output_tokens=500,
        )
        return CourseRuntime(
            service,
            tmp_path / "checkpoints.db",
            approval_required is not False,
            1,
            1,
            AdaptCourseWording(model, max_output_tokens=500),
        )

    monkeypatch.setattr(courses, "build_course_runtime", runtime)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "course",
            "Intégrales",
            "--curriculum",
            "official-mp",
            "--sections",
            "1",
            "--tex-only",
            "--thread-id",
            "auto-course",
            "--yes",
            "--auto-recover",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Auto-recover 1/5" in result.output + result.stderr
    assert model.generate_attempts == 3
    assert (tmp_path / "auto-course" / "course.tex").exists()
    assert model.tasks == ["plan", "generate", "generate", "generate", "audit"]


def test_importing_course_cli_does_not_initialize_checkpoint_serialization() -> None:
    # A fresh process catches eager imports hidden by the test suite's strict-msgpack setup.
    import os
    import subprocess
    import sys

    environment = dict(os.environ)
    environment.pop("LANGGRAPH_STRICT_MSGPACK", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import hermes_edu.interfaces.cli.courses; "
            "assert 'langgraph.checkpoint.serde.jsonplus' not in sys.modules",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
