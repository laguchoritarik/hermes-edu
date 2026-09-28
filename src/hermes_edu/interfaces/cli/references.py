"""Thin commands for the personal PDF reference library."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from hermes_edu.application.use_cases.reference_library import ReferenceLibrary
from hermes_edu.bootstrap import build_reference_library, repository_root
from hermes_edu.config.settings import load_settings
from hermes_edu.domain.errors import HermesError
from hermes_edu.domain.models.reference import ReferenceFilters
from hermes_edu.interfaces.reference_results import reference_search_payload

references_app = typer.Typer(help="Add and search personal PDF references.")


def _library() -> ReferenceLibrary:
    return build_reference_library(load_settings(), root=repository_root())


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def _error(exc: HermesError) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(1) from exc


@references_app.command("add")
def add(paths: list[Path]) -> None:
    """Add one or several PDFs from the configured data directory."""
    try:
        _emit([asdict(reference) for reference in _library().import_many(tuple(paths))])
    except HermesError as exc:
        _error(exc)


@references_app.command("add-directory")
def add_directory(directory: Path) -> None:
    """Add all PDFs in a configured data subdirectory."""
    try:
        _emit([asdict(reference) for reference in _library().import_directory(directory)])
    except HermesError as exc:
        _error(exc)


@references_app.command("list")
def list_references() -> None:
    try:
        _emit([asdict(reference) for reference in _library().list()])
    except HermesError as exc:
        _error(exc)


@references_app.command("get")
def get_reference(document_id: str) -> None:
    try:
        _emit(asdict(_library().get(document_id)))
    except HermesError as exc:
        _error(exc)


@references_app.command("search")
def search_references(
    query: str,
    top_k: int | None = typer.Option(None, min=1),
    document_id: Annotated[list[str] | None, typer.Option()] = None,
    preferred_only: bool = False,
    purpose: str = "",
    chapter: str = "",
    section: str = "",
) -> None:
    try:
        filters = ReferenceFilters(
            document_ids=tuple(document_id or ()),
            preferred_only=preferred_only,
            chapter=chapter,
            section=section,
        )
        _emit(
            reference_search_payload(
                _library().search(query, top_k=top_k, filters=filters, purpose=purpose)
            )
        )
    except HermesError as exc:
        _error(exc)


@references_app.command("disable")
def disable(document_id: str) -> None:
    try:
        _emit(asdict(_library().set_enabled(document_id, False)))
    except HermesError as exc:
        _error(exc)


@references_app.command("enable")
def enable(document_id: str) -> None:
    try:
        _emit(asdict(_library().set_enabled(document_id, True)))
    except HermesError as exc:
        _error(exc)


@references_app.command("prefer")
def prefer(document_id: str, preferred: bool = True) -> None:
    try:
        _emit(asdict(_library().set_preferred(document_id, preferred)))
    except HermesError as exc:
        _error(exc)


@references_app.command("remove")
def remove(document_id: str) -> None:
    try:
        _library().remove(document_id)
        _emit({"removed": document_id})
    except HermesError as exc:
        _error(exc)


@references_app.command("reindex")
def reindex(document_id: str) -> None:
    try:
        _emit(asdict(_library().reindex(document_id)))
    except HermesError as exc:
        _error(exc)
