"""Debug CLI for the generic BrowserService."""

from typing import Annotated

import typer

from hermes_edu.bootstrap import build_browser_service, build_reference_library, repository_root
from hermes_edu.config.settings import load_settings
from hermes_edu.domain.errors import HermesError

browser_app = typer.Typer(help="Debug the Hermes browser tool.")


def _browser_service(*, visible: bool = False):
    settings = load_settings()
    root = repository_root()
    from hermes_edu.bootstrap import ReferenceLibraryChatAdapter

    return build_browser_service(
        settings,
        root=root,
        visible=visible,
        reference_ingestion=ReferenceLibraryChatAdapter(
            build_reference_library(settings, root=root)
        ),
    )


@browser_app.command("open")
def open_url(
    url: str,
    *,
    visible: bool = typer.Option(False, help="Show Chromium"),
) -> None:
    """Open a URL and print a compact observation."""
    try:
        typer.echo(_browser_service(visible=visible).open(url).compact_summary())
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@browser_app.command("inspect")
def inspect_url(
    url: str,
    *,
    visible: bool = typer.Option(False, help="Show Chromium"),
) -> None:
    """Open and read a URL."""
    try:
        service = _browser_service(visible=visible)
        service.open(url)
        typer.echo(service.read().compact_summary())
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@browser_app.command("screenshot")
def screenshot(
    url: str,
    *,
    full_page: bool = typer.Option(False),
    visible: bool = typer.Option(False, help="Show Chromium"),
) -> None:
    """Open a URL and capture a screenshot."""
    try:
        service = _browser_service(visible=visible)
        service.open(url)
        typer.echo(service.screenshot(full_page=full_page).compact_summary())
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@browser_app.command("download")
def download(
    url: str,
    *,
    add_reference: Annotated[
        bool, typer.Option(help="Pass the downloaded PDF to the reference library")
    ] = False,
) -> None:
    """Download a URL into the controlled browser session directory."""
    try:
        service = _browser_service()
        observation = service.download(url=url)
        if add_reference:
            if observation.download is None:
                raise typer.BadParameter("No download was captured")
            document_id = service.ingest_download(observation.download.id)
            typer.echo(f"{observation.compact_summary()}\nReference: {document_id}")
        else:
            typer.echo(observation.compact_summary())
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@browser_app.command("close")
def close() -> None:
    """Close a debug browser session."""
    try:
        typer.echo(_browser_service().close().compact_summary())
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
