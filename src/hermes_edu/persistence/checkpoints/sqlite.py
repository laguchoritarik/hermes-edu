"""Strict-msgpack SQLite checkpoint factory."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from hermes_edu.domain.errors import ValidationError

if TYPE_CHECKING:
    from langgraph.checkpoint.sqlite import SqliteSaver


@contextmanager
def sqlite_checkpointer(path: Path) -> Generator[SqliteSaver, None, None]:
    """Open a durable checkpointer only with strict deserialization enabled."""
    if os.environ.get("LANGGRAPH_STRICT_MSGPACK", "").lower() != "true":
        raise ValidationError("Set LANGGRAPH_STRICT_MSGPACK=true before opening checkpoints")
    from langgraph.checkpoint.serde import _msgpack
    from langgraph.checkpoint.sqlite import SqliteSaver

    if not _msgpack.STRICT_MSGPACK_ENABLED:
        raise ValidationError("LangGraph was imported before strict msgpack was enabled")
    path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver
