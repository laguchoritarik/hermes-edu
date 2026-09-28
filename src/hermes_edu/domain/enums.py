"""Vocabulary shared by the v0.1 mathematics TD domain."""

from enum import StrEnum


class DocumentType(StrEnum):
    TD = "td"


class Severity(StrEnum):
    INFO = "info"
    ERROR = "error"
    WARNING = "warning"
    BLOCKER = "blocker"
