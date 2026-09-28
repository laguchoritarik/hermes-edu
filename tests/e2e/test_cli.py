"""CLI happy path with public knowledge and a scripted offline model."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hermes_edu.application.ports.llm import ModelRequest, ModelResponse, ModelUsage
from hermes_edu.bootstrap import Runtime, build_runtime
from hermes_edu.config.settings import Settings
from hermes_edu.interfaces.cli import app as cli


class OfflineModel:
    def complete_json(self, request: ModelRequest) -> ModelResponse:
        if request.task == "plan":
            content = json.dumps(
                {
                    "title": "Reduction",
                    "exercises": [
                        {
                            "title": "Eigenvalues",
                            "objective": "Compute eigenvalues",
                            "difficulty": 1,
                        }
                    ],
                }
            )
        elif request.task == "generate":
            content = json.dumps(
                {
                    "title": "Reduction",
                    "exercises": [
                        {
                            "title": "Eigenvalues",
                            "statement": "Find eigenvalues of diag(1,2)",
                            "solution": "The eigenvalues are 1 and 2.",
                            "source_ids": ["sample-mp-reduction"],
                        }
                    ],
                }
            )
        else:
            content = '{"issues":[]}'
        return ModelResponse(content, ModelUsage("offline", "fixed", 3, 2, 0, 1, 0.0))


def test_cli_indexes_example_and_generates_tex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).parents[2]
    settings = Settings(
        hermes_db_path=tmp_path / "knowledge.db",
        hermes_checkpoint_db_path=tmp_path / "checkpoints.db",
        hermes_workspace_dir=tmp_path / "workspace",
        hermes_embedding_provider="deterministic",
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "repository_root", lambda: root)

    def offline_runtime(
        current: Settings, *, tex_only: bool, approval_required: bool | None
    ) -> Runtime:
        return build_runtime(
            current,
            root=root,
            llm=OfflineModel(),
            tex_only=tex_only,
            approval_required=approval_required,
        )

    monkeypatch.setattr(cli, "build_runtime", offline_runtime)
    runner = CliRunner()
    indexed = runner.invoke(cli.app, ["ingest", "--example"])
    assert indexed.exit_code == 0, indexed.output
    generated = runner.invoke(
        cli.app,
        ["td", "Reduction", "--exercises", "1", "--yes", "--tex-only", "--thread-id", "cli-test"],
    )
    assert generated.exit_code == 0, generated.output
    assert (tmp_path / "workspace" / "cli-test" / "td.tex").is_file()
    assert '"input_tokens": 9' in generated.output
