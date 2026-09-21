"""Small, reusable wrapper around the Gmail API."""

from __future__ import annotations

import base64
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

class GmailService:
    """Expose Gmail operations with application-friendly return values."""

    def __init__(self, credentials: Credentials | None = None) -> None:
        self.credentials = credentials
        self._service: Resource | None = None

    def authenticate(self) -> Resource:
        """Authenticate and return the Gmail API client."""
        if self._service is None:
            if self.credentials is None:
                raise ValueError("Google credentials are required")
            self._service = build(
                "gmail", "v1", credentials=self.credentials, cache_discovery=False
            )
        return self._service

    def list_messages(
        self, max_results: int = 20, query: str | None = None
    ) -> list[dict[str, str]]:
        """Return a normalized list of messages from the authenticated user."""
        service = self.authenticate()
        response = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query)
            .execute()
        )
        return [
            self.get_message(item["id"])
            for item in response.get("messages", [])
        ]

    def get_message(self, message_id: str) -> dict[str, str]:
        """Get one message and flatten its useful headers and text body."""
        message = (
            self.authenticate()
            .users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = message.get("payload", {})
        headers = {
            header["name"].lower(): header.get("value", "")
            for header in payload.get("headers", [])
        }
        return {
            "id": message["id"],
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "body": self._extract_body(payload),
            "date": headers.get("date", ""),
        }

    def get_attachments(self, message_id: str) -> list[dict[str, Any]]:
        """Return attachment metadata and URL-safe base64 encoded content."""
        service = self.authenticate()
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        attachments: list[dict[str, Any]] = []

        for part in self._walk_parts(message.get("payload", {})):
            attachment_id = part.get("body", {}).get("attachmentId")
            filename = part.get("filename")
            if not attachment_id or not filename:
                continue
            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )
            attachments.append(
                {
                    "id": attachment_id,
                    "filename": filename,
                    "mime_type": part.get("mimeType", "application/octet-stream"),
                    "size": attachment.get("size", 0),
                    "content_base64": attachment.get("data", ""),
                }
            )
        return attachments

    def mark_as_read(self, message_id: str) -> bool:
        """Remove the UNREAD label from a message."""
        self.authenticate().users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        return True

    # ── Push notifications (watch / webhook) ────────────────────────────

    def watch(self, topic_name: str, label_ids: list[str] | None = None) -> dict[str, Any]:
        """Start receiving push notifications for the user's mailbox.

        Args:
            topic_name: A fully-qualified Google Cloud Pub/Sub topic,
                        e.g. ``projects/my-project/topics/gmail-push``.
            label_ids: Optional label filter (default: ``["INBOX"]``).

        Returns:
            Dict with ``history_id`` and ``expiration`` (ms epoch).
            The watch expires after ~7 days and must be renewed.
        """
        body: dict[str, Any] = {
            "topicName": topic_name,
            "labelIds": label_ids or ["INBOX"],
        }
        response = (
            self.authenticate()
            .users()
            .watch(userId="me", body=body)
            .execute()
        )
        return {
            "history_id": response.get("historyId"),
            "expiration": response.get("expiration"),
        }

    def stop_watch(self) -> bool:
        """Cancel the current push notification subscription."""
        self.authenticate().users().stop(userId="me").execute()
        return True

    # ── History-based sync (incremental) ────────────────────────────────

    def get_history_changes(
        self,
        start_history_id: str,
        history_types: list[str] | None = None,
        label_id: str | None = None,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Fetch mailbox changes since *start_history_id*.

        Args:
            start_history_id: The ``historyId`` returned by a previous
                ``watch()`` or ``list_messages()`` call.
            history_types: E.g. ``["messageAdded", "labelAdded"]``.
            label_id: Only return history for this label.
            max_results: Page size.

        Returns:
            ``{"history_id": "<latest>", "messages_added": [...], ...}``
        """
        params: dict[str, Any] = {
            "userId": "me",
            "startHistoryId": start_history_id,
            "maxResults": max_results,
        }
        if history_types:
            params["historyTypes"] = history_types
        if label_id:
            params["labelId"] = label_id

        response = (
            self.authenticate().users().history().list(**params).execute()
        )

        messages_added: list[dict[str, str]] = []
        messages_deleted: list[str] = []
        labels_added: list[dict[str, Any]] = []
        labels_removed: list[dict[str, Any]] = []

        for record in response.get("history", []):
            for item in record.get("messagesAdded", []):
                msg = item.get("message", {})
                messages_added.append(
                    {"id": msg["id"], "thread_id": msg.get("threadId", "")}
                )
            for item in record.get("messagesDeleted", []):
                messages_deleted.append(item.get("message", {}).get("id", ""))
            for item in record.get("labelsAdded", []):
                labels_added.append(
                    {
                        "message_id": item.get("message", {}).get("id", ""),
                        "labels": item.get("labelIds", []),
                    }
                )
            for item in record.get("labelsRemoved", []):
                labels_removed.append(
                    {
                        "message_id": item.get("message", {}).get("id", ""),
                        "labels": item.get("labelIds", []),
                    }
                )

        return {
            "history_id": response.get("historyId", start_history_id),
            "messages_added": messages_added,
            "messages_deleted": messages_deleted,
            "labels_added": labels_added,
            "labels_removed": labels_removed,
        }

    def list_unread_messages(self, max_results: int = 20) -> list[dict[str, str]]:
        """Convenience: return unread INBOX messages."""
        return self.list_messages(max_results=max_results, query="is:unread in:inbox")

    def get_profile(self) -> dict[str, Any]:
        """Return the authenticated user's Gmail profile (email, historyId)."""
        profile = (
            self.authenticate().users().getProfile(userId="me").execute()
        )
        return {
            "email": profile.get("emailAddress", ""),
            "messages_total": profile.get("messagesTotal", 0),
            "threads_total": profile.get("threadsTotal", 0),
            "history_id": profile.get("historyId", ""),
        }

    @classmethod
    def _extract_body(cls, payload: dict[str, Any]) -> str:
        parts = cls._walk_parts(payload)
        plain_parts = [p for p in parts if p.get("mimeType") == "text/plain"]
        candidates = plain_parts or [
            p for p in parts if p.get("mimeType") == "text/html"
        ]
        for part in candidates:
            data = part.get("body", {}).get("data")
            if data:
                return cls._decode(data)
        data = payload.get("body", {}).get("data")
        return cls._decode(data) if data else ""

    @classmethod
    def _walk_parts(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        for part in payload.get("parts", []):
            parts.append(part)
            parts.extend(cls._walk_parts(part))
        return parts

    @staticmethod
    def _decode(data: str) -> str:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding).decode(
            "utf-8", errors="replace"
        )
