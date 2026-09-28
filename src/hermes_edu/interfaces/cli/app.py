"""Thin Typer entrypoint for local indexing and TD workflows."""

# LangGraph's invoke overloads retain unknown generic parameters in its published typing.
# pyright: reportUnknownMemberType=false

import json
import shutil
import uuid
from pathlib import Path
from typing import Annotated

import typer

from hermes_edu.bootstrap import build_graph, build_knowledge, build_runtime, repository_root
from hermes_edu.config.paths import resolved_path
from hermes_edu.config.settings import load_settings
from hermes_edu.domain.errors import HermesError
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.domain.models.request import TDRequest
from hermes_edu.interfaces.cli.browser import browser_app
from hermes_edu.interfaces.cli.chat import chat_command, prompt_command
from hermes_edu.interfaces.cli.courses import generate_course, resume_course
from hermes_edu.interfaces.cli.curriculum import curriculum_app
from hermes_edu.interfaces.cli.references import references_app
from hermes_edu.knowledge.ingestion.base import load_document
from hermes_edu.orchestration.state import decode_result, encode_request
from hermes_edu.persistence.checkpoints.sqlite import sqlite_checkpointer

app = typer.Typer(help="Hermes Edu: index sources and generate mathematics courses and TDs.")
app.add_typer(references_app, name="references")
app.add_typer(curriculum_app, name="curriculum")
app.add_typer(browser_app, name="browser")
app.command("course")(generate_course)
app.command("course-resume")(resume_course)
app.command("chat")(chat_command)
app.command("prompt")(prompt_command)


@app.command()
def doctor() -> None:
    """Report local readiness without exposing secrets."""
    settings = load_settings()
    root = repository_root()
    typer.echo(
        json.dumps(
            {
                "database": str(resolved_path(root, settings.hermes_db_path)),
                "checkpoint_database": str(resolved_path(root, settings.hermes_checkpoint_db_path)),
                "deepseek_key_configured": bool(settings.deepseek_api_key),
                "xelatex_available": shutil.which(settings.hermes_latex_engine) is not None,
                "strict_msgpack": settings.langgraph_strict_msgpack,
            },
            indent=2,
        )
    )


@app.command()
def ingest(
    path: Annotated[Path | None, typer.Argument()] = None,
    *,
    example: bool = typer.Option(False, help="Index the bundled synthetic MP example"),
    source_id: str = typer.Option("local-source"),
    title: str = typer.Option("Local source"),
    license: str = typer.Option("user-provided"),
    curriculum: str = typer.Option("sample-mp"),
    track: str = typer.Option("MP"),
    kind: str = typer.Option("curriculum"),
    source_url: str | None = typer.Option(None, help="Canonical source URL retained in citations"),
) -> None:
    """Index one source, reusing vectors for unchanged chunks."""
    settings = load_settings()
    root = repository_root()
    if example:
        if path is not None:
            raise typer.BadParameter("Do not pass a path with --example")
        allowed_root = root / "examples" / "curriculum"
        path = allowed_root / "math-mp-reduction.md"
        source_id, title, license, curriculum, track, kind = (
            "sample-mp-reduction",
            "Synthetic MP reduction example",
            "CC0-1.0",
            "sample-mp",
            "MP",
            "curriculum",
        )
    else:
        if path is None:
            raise typer.BadParameter("Provide a source path or --example")
        allowed_root = resolved_path(root, settings.hermes_data_dir)
    try:
        document = load_document(
            path,
            allowed_root=allowed_root,
            source_id=source_id,
            title=title,
            license=license,
            context=LearningContext(curriculum, track),
            kind=kind,
            source_url=source_url,
        )
        count = build_knowledge(settings, root=root).index(document)
    except HermesError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Indexed {source_id}: {count} new or changed chunks")


def _print_state(state: dict[str, object], thread_id: str) -> None:
    if "__interrupt__" in state:
        typer.echo(f"Plan awaiting approval. Resume with: hermes-edu resume {thread_id} approve")
    elif "result_json" in state and isinstance(state["result_json"], str):
        result = decode_result(state["result_json"])
        typer.echo(
            json.dumps(
                {
                    "thread_id": result.thread_id,
                    "artifacts": [artifact.path for artifact in result.artifacts],
                    "source_ids": [source.source_id for source in result.sources],
                    "revisions": result.revisions,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cached_tokens": result.cached_tokens,
                    "estimated_cost_usd": result.estimated_cost_usd,
                    "usage": [
                        {
                            "model": usage.model,
                            "task": usage.task,
                            "provider": usage.provider,
                            "input_tokens": usage.input_tokens,
                            "output_tokens": usage.output_tokens,
                            "cached_tokens": usage.cached_tokens,
                            "latency_ms": usage.latency_ms,
                            "estimated_cost_usd": usage.estimated_cost_usd,
                            "price_basis": usage.price_basis,
                        }
                        for usage in result.usage
                    ],
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"Thread {thread_id} ended without artifacts")


@app.command("td")
def generate_td(
    topic: str,
    *,
    curriculum: str = typer.Option("sample-mp"),
    track: str = typer.Option("MP"),
    exercises: int = typer.Option(3, min=1, max=12),
    yes: bool = typer.Option(False, help="Explicitly skip interactive plan approval"),
    tex_only: bool = typer.Option(False, help="Generate TeX without compiling a PDF"),
    thread_id: str | None = typer.Option(None),
) -> None:
    """Start a checkpointed TD generation thread."""
    settings = load_settings()
    try:
        request = TDRequest(topic, LearningContext(curriculum, track), exercises)
        runtime = build_runtime(
            settings, tex_only=tex_only, approval_required=False if yes else None
        )
        identifier = thread_id or uuid.uuid4().hex
        with sqlite_checkpointer(runtime.checkpoint_path) as saver:
            graph = build_graph(runtime).compile(checkpointer=saver)
            if graph.get_state({"configurable": {"thread_id": identifier}}).values:
                raise typer.BadParameter(
                    f"Thread {identifier} already exists; use the resume command"
                )
            state = graph.invoke(
                {"request_json": encode_request(request), "thread_id": identifier},
                config={"configurable": {"thread_id": identifier}},
            )
        _print_state(state, identifier)
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def resume(
    thread_id: str,
    decision: str = typer.Argument(help="approve or reject"),
    *,
    tex_only: bool = typer.Option(False),
) -> None:
    """Resume an existing plan approval from its persisted checkpoint."""
    if decision not in {"approve", "reject"}:
        raise typer.BadParameter("Decision must be approve or reject")
    settings = load_settings()
    try:
        runtime = build_runtime(settings, tex_only=tex_only, approval_required=True)
        from langgraph.types import Command

        with sqlite_checkpointer(runtime.checkpoint_path) as saver:
            graph = build_graph(runtime).compile(checkpointer=saver)
            if not graph.get_state({"configurable": {"thread_id": thread_id}}).values:
                raise typer.BadParameter(f"No checkpoint found for thread {thread_id}")
            state = graph.invoke(
                Command(resume=decision), config={"configurable": {"thread_id": thread_id}}
            )
        _print_state(state, thread_id)
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
