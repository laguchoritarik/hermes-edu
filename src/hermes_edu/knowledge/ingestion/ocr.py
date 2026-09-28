"""PDF to LaTeX API adapter shared by text and scanned reference imports."""

import time

import httpx

from hermes_edu.domain.errors import ValidationError


class ILoveMyLatexOCR:
    version = "ilovemylatex-raw-v2"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: int = 120,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    def convert(self, pdf_bytes: bytes) -> str:
        """Upload PDF bytes using the API contract, then retrieve the generated LaTeX."""
        if not self._api_key:
            raise ValidationError("PDF to LaTeX conversion requires ILOVEMYLATEX_API_KEY")
        headers = {"X-API-Key": self._api_key}
        try:
            with self._client or httpx.Client(timeout=30) as client:
                upload = client.post(
                    f"{self._base_url}/documents/upload",
                    headers={
                        **headers,
                        "X-Filename": "reference.pdf",
                        "Content-Type": "application/pdf",
                    },
                    content=pdf_bytes,
                    timeout=min(self._timeout, 120),
                )
                upload.raise_for_status()
                document_id = upload.json().get("file_id")
                if not isinstance(document_id, str) or not document_id:
                    raise ValidationError("OCR upload returned no document ID")
                deadline = time.monotonic() + self._timeout
                while time.monotonic() < deadline:
                    response = client.get(
                        f"{self._base_url}/documents/{document_id}/status", headers=headers
                    )
                    response.raise_for_status()
                    status = response.json().get("status")
                    if status == "completed":
                        result = client.get(
                            f"{self._base_url}/documents/{document_id}/result", headers=headers
                        )
                        result.raise_for_status()
                        if not result.text.strip():
                            raise ValidationError("OCR returned empty LaTeX")
                        return result.text
                    if status in {"failed", "cancelled"}:
                        raise ValidationError(f"OCR conversion {status}")
                    time.sleep(2)
        except httpx.HTTPStatusError as exc:
            raise ValidationError(
                f"OCR service rejected request: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ValidationError(f"OCR service request failed: {type(exc).__name__}") from exc
        raise ValidationError("OCR conversion timed out")
