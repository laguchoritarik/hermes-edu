"""Failures meaningful to callers regardless of delivery mechanism."""


class HermesError(Exception):
    """Base error for expected Hermes failures."""


class ValidationError(HermesError):
    """Input or generated structured content violates a contract."""


class SourceNotFoundError(HermesError):
    """No suitable indexed curriculum or knowledge source exists."""


class GenerationError(HermesError):
    """A model call or document generation failed."""


class AuditExhaustedError(HermesError):
    """The draft did not pass audit within the revision budget."""


class CompilationError(HermesError):
    """Controlled TeX compilation failed."""
