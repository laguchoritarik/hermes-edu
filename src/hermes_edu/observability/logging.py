"""Structured events at the reference-library application boundary."""

import structlog


class StructlogReferenceEvents:
    def __init__(self) -> None:
        self._logger = structlog.get_logger("hermes.references")

    def info(self, event: str, **fields: object) -> None:
        self._logger.info(event, **fields)

    def warning(self, event: str, **fields: object) -> None:
        self._logger.warning(event, **fields)
