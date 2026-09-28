"""Resolve paths against an explicit repository root and enforce confinement."""

from pathlib import Path

from hermes_edu.domain.errors import ValidationError


def resolved_path(root: Path, configured: Path) -> Path:
    return (root / configured).resolve() if not configured.is_absolute() else configured.resolve()


def confined_path(root: Path, candidate: Path) -> Path:
    """Reject symlink and traversal escapes from a configured root."""
    safe_root = root.resolve()
    safe_candidate = candidate.resolve()
    if not safe_candidate.is_relative_to(safe_root):
        raise ValidationError(f"Path is outside allowed root: {candidate}")
    return safe_candidate
