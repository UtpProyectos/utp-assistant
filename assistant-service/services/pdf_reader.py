"""Bounded text extraction for PDF attachments."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

from pypdf import PdfReader


class PdfTextExtractor:
    def __init__(self, max_chars: int = 12_000) -> None:
        self.max_chars = max_chars

    def extract(self, attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._extract(item) for item in attachments[:5]]

    def _extract(self, attachment: dict[str, Any]) -> dict[str, Any]:
        filename = str(attachment.get("filename") or "archivo.pdf")
        try:
            data = str(attachment.get("content_base64") or "")
            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
            reader = PdfReader(BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            if not text:
                return {
                    "filename": filename,
                    "status": "empty",
                    "content": "",
                    "message": "El PDF no contiene texto extraíble; puede requerir OCR.",
                }
            truncated = len(text) > self.max_chars
            return {
                "filename": filename,
                "status": "processed",
                "content": text[: self.max_chars],
                "truncated": truncated,
            }
        except Exception as exc:
            return {
                "filename": filename,
                "status": "failed",
                "content": "",
                "message": str(exc),
            }
