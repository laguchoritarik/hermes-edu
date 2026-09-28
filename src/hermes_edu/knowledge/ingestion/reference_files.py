"""Allowlisted local PDF access and retained originals for explicit reindexing."""

import os
import tempfile
from pathlib import Path

from hermes_edu.config.paths import confined_path
from hermes_edu.domain.errors import ValidationError


class LocalReferenceFiles:
    def __init__(self, allowed_root: Path, retained_root: Path, *, max_bytes: int) -> None:
        self._allowed_root = allowed_root.resolve()
        self._retained_root = retained_root.resolve()
        self._max_bytes = max_bytes
        self._retained_root.mkdir(parents=True, exist_ok=True)

    def read(self, path: Path) -> bytes:
        safe = confined_path(self._allowed_root, path)
        if not safe.is_file() or safe.suffix.lower() != ".pdf":
            raise ValidationError("Reference must be a PDF inside HERMES_DATA_DIR")
        if not 0 < safe.stat().st_size <= self._max_bytes:
            raise ValidationError("Reference PDF exceeds the configured size limit")
        content = safe.read_bytes()
        if not content.startswith(b"%PDF-"):
            raise ValidationError("Reference is not a valid PDF header")
        return content

    def list_pdfs(self, directory: Path) -> tuple[Path, ...]:
        safe = confined_path(self._allowed_root, directory)
        if not safe.is_dir():
            raise ValidationError("Reference directory does not exist")
        return tuple(
            path
            for path in sorted(safe.rglob("*"))
            if path.is_file()
            and path.suffix.lower() == ".pdf"
            and path.resolve().is_relative_to(self._allowed_root)
        )

    def _retained_path(self, content_hash: str) -> Path:
        if len(content_hash) != 64 or any(
            character not in "0123456789abcdef" for character in content_hash
        ):
            raise ValidationError("Invalid PDF content hash")
        return self._retained_root / f"{content_hash}.pdf"

    def retain(self, content_hash: str, content: bytes) -> None:
        destination = self._retained_path(content_hash)
        if destination.exists():
            return
        with tempfile.NamedTemporaryFile(dir=self._retained_root, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)

    def retained(self, content_hash: str) -> bytes:
        path = self._retained_path(content_hash)
        if not path.is_file():
            raise ValidationError("Retained PDF is missing; import it again")
        return path.read_bytes()

    def remove(self, content_hash: str) -> None:
        self._retained_path(content_hash).unlink(missing_ok=True)
