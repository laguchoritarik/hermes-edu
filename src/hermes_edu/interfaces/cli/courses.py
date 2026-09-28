"""CLI creation and durable resume for the course workflow."""

from __future__ import annotations

# LangGraph exposes dynamically typed invoke and checkpoint values.
# pyright: reportUnknownMemberType=false
import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import typer

from hermes_edu.bootstrap import build_course_runtime, build_course_workflow
from hermes_edu.config.settings import load_settings
from hermes_edu.domain.errors import HermesError, ValidationError
from hermes_edu.domain.models.course import CourseRequest
from hermes_edu.domain.models.course_wording import CourseWordingPolicy
from hermes_edu.persistence.checkpoints.sqlite import sqlite_checkpointer

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.pregel import Pregel

    from hermes_edu.orchestration.graphs.course import CourseState


_AUTO_RECOVER_MAX_ATTEMPTS = 5
_UNRECOVERABLE_NEXT_NODES = frozenset({"latex_exhausted"})


def _show(state: Mapping[str, object], identifier: str) -> None:
    if "__interrupt__" in state:
        typer.echo(state.get("plan_json", ""))
        typer.echo(
            f"Plan awaiting approval. Resume with: hermes-edu course-resume {identifier} approve"
        )
    elif "result_json" in state:
        typer.echo(state["result_json"])
    else:
        typer.echo(f"Course {identifier}: rejected; no artifacts generated")


def _recoverable_next(graph: Pregel[CourseState], config: RunnableConfig) -> str:
    snapshot = graph.get_state(config)
    if not snapshot.values or not snapshot.next:
        return ""
    if set(snapshot.next).intersection(_UNRECOVERABLE_NEXT_NODES):
        return ""
    if any(task.interrupts for task in snapshot.tasks):
        return ""
    return ", ".join(snapshot.next)


def _invoke_with_auto_recover(
    invoke: Callable[[], object],
    *,
    graph: Pregel[CourseState],
    config: RunnableConfig,
    enabled: bool,
) -> dict[str, object]:
    attempts = 0
    while True:
        try:
            return cast(dict[str, object], invoke())
        except HermesError as exc:
            if not enabled:
                raise
            attempts += 1
            next_nodes = _recoverable_next(graph, config)
            if attempts > _AUTO_RECOVER_MAX_ATTEMPTS or not next_nodes:
                raise
            typer.echo(
                "Auto-recover "
                f"{attempts}/{_AUTO_RECOVER_MAX_ATTEMPTS}: {exc}. "
                f"Retrying checkpoint node(s): {next_nodes}",
                err=True,
            )

            def retry_checkpoint() -> object:
                return graph.invoke(None, config=config)

            invoke = retry_checkpoint


def _load_wording_file(path: Path) -> CourseState:
    """Snapshot the closed phrase list once; resume never rereads a changed file."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(80001)
        if len(raw) > 80000:
            raise ValidationError("Phrase file exceeds 80000 bytes")
        phrases = tuple(
            line.strip() for line in raw.decode("utf-8-sig").splitlines() if line.strip()
        )
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"Cannot read UTF-8 phrase file: {path}") from exc
    policy = CourseWordingPolicy(phrases)
    return {
        "wording_policy_json": json.dumps(asdict(policy), ensure_ascii=False),
        "wording_source": str(path.resolve()),
        "wording_sha256": sha256(raw).hexdigest(),
    }


def generate_course(
    topic: str,
    *,
    curriculum: str = typer.Option(..., help="Indexed official curriculum ID"),
    track: str = "MP",
    sections: int = typer.Option(6, min=1, max=12),
    document_id: Annotated[list[str] | None, typer.Option()] = None,
    yes: bool = typer.Option(False, help="Skip interactive plan approval"),
    auto_recover: bool = typer.Option(
        False,
        help="Retry failed checkpoint nodes automatically, up to a bounded limit.",
    ),
    tex_only: bool = False,
    thread_id: str | None = None,
    phrases_file: Annotated[
        Path | None, typer.Option(help="UTF-8 file of allowed transitions, one per line")
    ] = None,
) -> None:
    """Create a course using embedded-query curriculum and PDF reference retrieval."""
    identifier = thread_id or uuid.uuid4().hex
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            raise ValidationError(
                "Thread ID must contain 1-80 letters, digits, hyphens or underscores"
            )
        wording_state: CourseState = _load_wording_file(phrases_file) if phrases_file else {}
        request = CourseRequest(topic, curriculum, track, sections, tuple(document_id or ()))
        runtime = build_course_runtime(
            load_settings(), tex_only=tex_only, approval_required=False if yes else None
        )
        with sqlite_checkpointer(runtime.checkpoint_path) as saver:
            graph = build_course_workflow(runtime).compile(checkpointer=saver)
            config: RunnableConfig = {
                "configurable": {"thread_id": identifier},
                "recursion_limit": 100,
            }
            if graph.get_state(config).values:
                raise ValidationError(f"Thread {identifier} already exists; use course-resume")
            typer.echo(f"Course thread: {identifier}")
            initial_state: CourseState = {
                "workflow": "course",
                "request_json": json.dumps(asdict(request)),
                "thread_id": identifier,
                "tex_only": tex_only,
                "approval_required": runtime.approval_required,
            }
            initial_state.update(wording_state)
            state = _invoke_with_auto_recover(
                lambda: graph.invoke(initial_state, config=config),
                graph=graph,
                config=config,
                enabled=auto_recover,
            )
        _show(state, identifier)
    except HermesError as exc:
        typer.echo(f"Error: {exc}. Thread: {identifier}", err=True)
        raise typer.Exit(1) from exc


def resume_course(
    thread_id: str,
    decision: str = typer.Argument(
        "continue", help="approve, reject, or continue after a failed node"
    ),
    auto_recover: bool = typer.Option(
        False,
        help="Retry failed checkpoint nodes automatically, up to a bounded limit.",
    ),
) -> None:
    """Resume the stored plan or retry a failed node without regenerating completed sections."""
    if decision not in {"approve", "reject", "continue"}:
        raise typer.BadParameter("Decision must be approve, reject or continue")
    settings = load_settings()
    try:
        runtime = build_course_runtime(settings)
        from langgraph.types import Command

        with sqlite_checkpointer(runtime.checkpoint_path) as saver:
            graph = build_course_workflow(runtime).compile(checkpointer=saver)
            config: RunnableConfig = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 100,
            }
            snapshot = graph.get_state(config)
            if not snapshot.values or snapshot.values.get("workflow") != "course":
                raise ValidationError(f"No course checkpoint found for {thread_id}")
            # Compilation mode is part of the original request, not a resume-time default.
            runtime = build_course_runtime(
                settings,
                tex_only=snapshot.values.get("tex_only") is True,
                approval_required=snapshot.values.get(
                    "approval_required", settings.hermes_human_approval_required
                )
                is True,
            )
            graph = build_course_workflow(runtime).compile(checkpointer=saver)
            interrupted = any(task.interrupts for task in snapshot.tasks)
            if interrupted and decision == "continue":
                raise ValidationError("This course awaits plan approval: use approve or reject")
            if not interrupted and decision != "continue":
                raise ValidationError("No pending approval; use continue to retry the pending node")
            if not snapshot.next:
                _show(snapshot.values, thread_id)
                return
            command = Command(resume=decision) if interrupted else None
            state = _invoke_with_auto_recover(
                lambda: graph.invoke(command, config=config),
                graph=graph,
                config=config,
                enabled=auto_recover,
            )
        _show(state, thread_id)
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
