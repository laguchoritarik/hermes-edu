"""CLI access to provenance-preserving official curriculum retrieval."""

import json

import typer

from hermes_edu.bootstrap import build_knowledge, repository_root
from hermes_edu.config.settings import load_settings
from hermes_edu.domain.errors import HermesError
from hermes_edu.domain.models.curriculum import LearningContext
from hermes_edu.knowledge.retrieval.vector import SQLiteVectorRetriever

curriculum_app = typer.Typer(help="Search indexed curriculum sources.")


@curriculum_app.command("search")
def search(
    query: str,
    *,
    curriculum: str = typer.Option(..., help="Indexed curriculum identifier"),
    track: str = typer.Option("MP", help="Educational track"),
    top_k: int = typer.Option(5, min=1, max=20, help="Maximum matching chunks"),
) -> None:
    """Embed QUERY, then search only curriculum chunks in the selected context."""
    if not query.strip() or len(query) > 500:
        raise typer.BadParameter("Query must contain 1-500 characters")
    settings = load_settings()
    try:
        store = build_knowledge(settings, root=repository_root())
        hits = SQLiteVectorRetriever(
            store, store.embedding, min_score=settings.hermes_reference_min_score
        ).retrieve(query, LearningContext(curriculum, track), kind="curriculum", top_k=top_k)
    except HermesError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                "query": query,
                "curriculum": curriculum,
                "track": track,
                "kind": "curriculum",
                "status": "ok" if hits else "no_results",
                "hits": [
                    {
                        "chunk_id": hit.chunk_id,
                        "text": hit.text,
                        "score": hit.score,
                        "section": hit.section,
                        "source": {
                            "source_id": hit.source.source_id,
                            "title": hit.source.title,
                            "location": hit.source.location,
                            "license": hit.source.license,
                        },
                    }
                    for hit in hits
                ],
            },
            indent=2,
        )
    )
