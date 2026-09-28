"""Terminal adapter for the reusable Hermes chat service."""

from pathlib import Path
from typing import Annotated

import typer

from hermes_edu.application.use_cases.chat import ChatService
from hermes_edu.bootstrap import build_chat_service, repository_root
from hermes_edu.config.settings import load_settings
from hermes_edu.domain.errors import HermesError


def _service(
    *,
    tex_only: bool = False,
    auto_confirm: bool | None = None,
    browser: bool | None = None,
    browser_visible: bool = False,
) -> ChatService:
    settings = load_settings()
    return build_chat_service(
        settings,
        root=repository_root(),
        tex_only=tex_only,
        auto_confirm=auto_confirm or settings.hermes_chat_auto_confirm,
        browser_enabled=browser,
        browser_visible=browser_visible,
    )


def chat(
    *,
    resume: str | None = typer.Option(None, help="Session id to resume, or 'last'"),
    new: bool = typer.Option(False, "--new", help="Start a new session"),
    project: str | None = typer.Option(None, help="Project context id"),
    verbose: bool = typer.Option(False, help="Show session metadata"),
    auto_confirm: Annotated[
        bool | None, typer.Option(help="Run ready tasks without confirmation")
    ] = None,
    tex_only: bool = typer.Option(False, help="Generate TeX without compiling PDF"),
    browser: bool = typer.Option(False, help="Enable the browser tool for this chat"),
    browser_visible: bool = typer.Option(False, help="Show Chromium while Hermes acts"),
) -> None:
    """Start an interactive natural-language Hermes session."""
    service = (
        _service(
            tex_only=tex_only,
            auto_confirm=auto_confirm,
            browser=browser or browser_visible,
            browser_visible=browser_visible,
        )
        if browser or browser_visible
        else _service(tex_only=tex_only, auto_confirm=auto_confirm)
    )
    try:
        session = (
            service.start_session(project) if new or not resume else service.resume_session(resume)
        )
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo("Hermes Edu")
    if project:
        typer.echo(f"Projet : {project}")
    typer.echo(f"Session : {session.id}")
    if resume:
        typer.echo("Session restaurée.")
    typer.echo("Hermes > Que souhaitez-vous préparer ?")
    while True:
        try:
            message = typer.prompt("Vous")
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nHermes > Session sauvegardée.")
            return
        try:
            response = service.handle_message(session.id, message)
        except HermesError as exc:
            typer.echo(f"Hermes > Une erreur est survenue : {exc}")
            continue
        session = response.session
        if verbose:
            typer.echo(f"[{response.command}] session={session.id} status={session.status.value}")
        typer.echo(f"Hermes > {response.message}")
        if response.should_exit:
            return


def prompt(
    text: str | None = typer.Argument(None),
    *,
    file: Annotated[
        Path | None, typer.Option("--file", "-f", help="Read prompt text from a file")
    ] = None,
    project: Annotated[str | None, typer.Option(help="Project context id")] = None,
    auto_confirm: Annotated[
        bool | None, typer.Option(help="Run the generated task immediately")
    ] = None,
    tex_only: Annotated[bool, typer.Option(help="Generate TeX without compiling PDF")] = False,
    browser: Annotated[bool, typer.Option(help="Enable the browser tool")] = False,
    browser_visible: Annotated[bool, typer.Option(help="Show Chromium while Hermes acts")] = False,
) -> None:
    """Handle one natural-language request through the chat service."""
    if file is not None:
        text = file.read_text(encoding="utf-8")
    if not text:
        raise typer.BadParameter("Provide prompt text or --file")
    service = (
        _service(
            tex_only=tex_only,
            auto_confirm=auto_confirm,
            browser=browser or browser_visible,
            browser_visible=browser_visible,
        )
        if browser or browser_visible
        else _service(tex_only=tex_only, auto_confirm=auto_confirm)
    )
    try:
        response = service.handle_prompt(text, project_id=project)
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(response.message)


chat_command = chat
prompt_command = prompt
