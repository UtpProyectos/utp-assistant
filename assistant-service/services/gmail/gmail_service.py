"""Minimal Gmail client used by the polling process."""

from __future__ import annotations

import base64
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build


class GmailService:
    """Read matching messages and mark them as processed."""

    def __init__(self, credentials: Credentials) -> None:
        self.credentials = credentials
        self._service: Resource | None = None

    def list_messages(
        self, max_results: int = 20, query: str | None = None
    ) -> list[dict[str, Any]]:
        """Return matching messages with sender, subject, body and date."""
        response = self._api().users().messages().list(
            userId="me", maxResults=max_results, q=query
        ).execute()
        return [self._read_message(item["id"]) for item in response.get("messages", [])]

    def mark_as_read(self, message_id: str) -> None:
        self._api().users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()

    def _read_message(self, message_id: str) -> dict[str, Any]:
        message = self._api().users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        payload = message.get("payload", {})
        headers = {
            item["name"].lower(): item.get("value", "")
            for item in payload.get("headers", [])
        }
        raw_from = headers.get("from", "")
        sender_name, sender_email = parseaddr(raw_from)
        return {
            "id": message["id"],
            "thread_id": message.get("threadId", ""),
            "from": raw_from,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "subject": headers.get("subject", ""),
            "body": self._extract_body(payload),
            "date": self._normalize_date(headers.get("date", "")),
            "pdf_attachments": self._read_pdfs(message_id, payload),
        }

    def _read_pdfs(
        self, message_id: str, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        pdfs = []
        for part in self._walk_parts(payload):
            filename = str(part.get("filename") or "")
            is_pdf = filename.lower().endswith(".pdf") or part.get("mimeType") == "application/pdf"
            if not is_pdf:
                continue
            filename = filename or "archivo.pdf"

            body = part.get("body", {})
            attachment_id = body.get("attachmentId")
            data = body.get("data", "")
            if attachment_id:
                attachment = self._api().users().messages().attachments().get(
                    userId="me", messageId=message_id, id=attachment_id
                ).execute()
                data = attachment.get("data", "")
            if data:
                pdfs.append({"filename": filename, "content_base64": data})
            if len(pdfs) == 5:
                break
        return pdfs

    def _api(self) -> Resource:
        if self._service is None:
            self._service = build(
                "gmail", "v1", credentials=self.credentials, cache_discovery=False
            )
        return self._service

    @classmethod
    def _extract_body(cls, payload: dict[str, Any]) -> str:
        parts = cls._walk_parts(payload)
        candidates = [
            part
            for part in parts
            if part.get("mimeType") == "text/plain" and not part.get("filename")
        ]
        if not candidates:
            candidates = [
                part
                for part in parts
                if part.get("mimeType") == "text/html" and not part.get("filename")
            ]
        for part in candidates:
            if data := part.get("body", {}).get("data"):
                return cls._decode(data)
        data = payload.get("body", {}).get("data")
        return cls._decode(data) if data else ""

    @classmethod
    def _walk_parts(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        parts = []
        for part in payload.get("parts", []):
            parts.extend([part, *cls._walk_parts(part)])
        return parts

    @staticmethod
    def _decode(data: str) -> str:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
            "utf-8", errors="replace"
        )

    @staticmethod
    def _normalize_date(value: str) -> str:
        try:
            return parsedate_to_datetime(value).isoformat() if value else ""
        except (TypeError, ValueError):
            return value
