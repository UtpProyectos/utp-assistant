"""Periodic Gmail processing loop."""

from __future__ import annotations

import json
from typing import Any

from config import settings
from database import Database
from services.pdf_reader import PdfTextExtractor


class EmailPollingService:
    """Process unread messages once and persist the resulting actions."""

    TERMINAL_STATUSES = {"processed", "ignored"}
    ACTION_LABELS = {
        "leer_agenda": "Agenda consultada",
        "crear_reunion": "Reunión creada",
        "reagendar_reunion": "Reunión reagendada",
        "eliminar_reunion": "Reunión eliminada",
    }

    def __init__(
        self,
        gmail_service: Any,
        assistant: Any,
        database: Database,
        user_id: int,
        pdf_extractor: PdfTextExtractor | None = None,
    ) -> None:
        self.gmail = gmail_service
        self.assistant = assistant
        self.database = database
        self.user_id = user_id
        self.pdfs = pdf_extractor or PdfTextExtractor()

    def process_new_emails(self) -> dict[str, int]:
        emails = self.gmail.list_messages(settings.gmail_max_results, settings.gmail_query)
        result = {
            "found": len(emails),
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "actions_completed": 0,
            "actions_failed": 0,
        }
        print(f"[Gmail] encontrados={len(emails)}")

        for email in reversed(emails):
            existing = self.database.get_gmail_message_by_gmail_id(self.user_id, email["id"])
            if existing and existing["status"] in self.TERMINAL_STATUSES:
                result["skipped"] += 1
                continue

            message_id = self.database.save_gmail_message(
                user_id=self.user_id,
                gmail_message_id=email["id"],
                thread_id=email.get("thread_id"),
                sender=email.get("sender_email") or email.get("from"),
                subject=email.get("subject"),
                received_at=email.get("date") or None,
            )
            self.database.update_gmail_message_status(message_id, "queued")

            try:
                email["pdfs"] = self.pdfs.extract(email.pop("pdf_attachments", []))
                for pdf in email["pdfs"]:
                    print(
                        f"[PDF] {pdf['filename']} | {pdf['status']} | "
                        f"caracteres={len(pdf.get('content', ''))}"
                    )
                    if pdf.get("content"):
                        preview = str(pdf["content"])[:1000]
                        print(f"[PDF] texto_extraido={preview}")
                ai_result = self.assistant.procesar_correo(email)
                self._save_actions(message_id, email, ai_result)

                for action in ai_result.get("acciones", []):
                    key = "actions_completed" if action.get("status") == "completed" else "actions_failed"
                    result[key] += 1

                self.gmail.mark_as_read(email["id"])
                self.database.update_gmail_message_status(message_id, "processed")
                result["processed"] += 1
                print(
                    "[Assistant] respuesta="
                    + json.dumps(ai_result, ensure_ascii=False, default=str)
                )
            except Exception as exc:
                self._save_error(message_id, email, exc)
                result["failed"] += 1
                print(f"[Assistant] ERROR | {email.get('subject') or '(sin asunto)'} | {exc}")

        print(f"[Gmail] fin={result}")
        return result

    def _save_actions(
        self, message_id: int, email: dict[str, Any], ai_result: dict[str, Any]
    ) -> None:
        actions = ai_result.get("acciones", [])
        if not actions:
            self._save_action(
                message_id,
                "email_analysis",
                "assistant",
                f"Correo analizado: {email.get('subject') or '(sin asunto)'}",
                "completed",
                ai_result,
            )
            return

        for action in actions:
            action_type = action.get("accion", "calendar_action")
            status = action.get("status", "failed")
            result = action.get("resultado", {})
            event = result.get("event", {}) if isinstance(result, dict) else {}
            label = self.ACTION_LABELS.get(action_type, "Acción de Calendar")
            subject = event.get("title") or email.get("subject") or "Sin asunto"
            title = f"{label}: {subject}" if status == "completed" else f"Falló {label.lower()}: {subject}"
            self._save_action(
                message_id, action_type, "calendar", title, status, ai_result, result
            )

    def _save_action(
        self,
        message_id: int,
        action_type: str,
        service: str,
        title: str,
        status: str,
        ai_result: dict[str, Any],
        tool_result: dict[str, Any] | None = None,
    ) -> None:
        action_id = self.database.create_action(
            user_id=self.user_id,
            gmail_message_db_id=message_id,
            action_type=action_type,
            service=service,
            title=title,
            input_data={"gmail_message_id": message_id},
        )
        completed = status == "completed"
        self.database.update_action_status(
            action_id,
            "completed" if completed else "failed",
            output_data={
                "tool_result": tool_result or {},
                "respuesta": ai_result.get("respuesta", ""),
                "usage": ai_result.get("usage", {}),
            } if completed else None,
            error_message=None if completed else str((tool_result or {}).get("message", "Error")),
        )

    def _save_error(self, message_id: int, email: dict[str, Any], exc: Exception) -> None:
        action_id = self.database.create_action(
            user_id=self.user_id,
            gmail_message_db_id=message_id,
            action_type="email_processing",
            service="assistant",
            title=f"Error procesando: {email.get('subject') or '(sin asunto)'}",
            input_data={"gmail_message_id": email["id"]},
        )
        self.database.update_action_status(action_id, "failed", error_message=str(exc))
        self.database.update_gmail_message_status(message_id, "failed")
