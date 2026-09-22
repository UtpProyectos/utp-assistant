"""Periodic Gmail processing loop."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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
        "crear_ticket_en_jira": "Ticket de Jira creado",
        "crear_proyecto_en_jira": "Proyecto de Jira registrado",
        "notificar_cambio_horario": "Cambio de horario notificado",
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
                self._notify_automatic_reschedule(email, ai_result)
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
            ticket = result.get("ticket", {}) if isinstance(result, dict) else {}
            project = result.get("project", {}) if isinstance(result, dict) else {}
            epic = project.get("epic", {}) if isinstance(project, dict) else {}
            jira_actions = {"crear_ticket_en_jira", "crear_proyecto_en_jira"}
            if action_type in jira_actions:
                service = "jira"
            elif action_type == "notificar_cambio_horario":
                service = "gmail"
            else:
                service = "calendar"
            label = self.ACTION_LABELS.get(action_type, "Acción del asistente")
            subject = (
                ticket.get("ticket_key")
                or epic.get("key")
                or event.get("title")
                or email.get("subject")
                or "Sin asunto"
            )
            title = (
                f"{label}: {subject}"
                if status == "completed"
                else f"Falló {label.lower()}: {subject}"
            )
            self._save_action(
                message_id, action_type, service, title, status, ai_result, result
            )

    def _notify_automatic_reschedule(
        self,
        email: dict[str, Any],
        ai_result: dict[str, Any],
    ) -> None:
        for action in list(ai_result.get("acciones", [])):
            result = action.get("resultado", {})
            if not (
                action.get("accion") == "crear_reunion"
                and action.get("status") == "completed"
                and isinstance(result, dict)
                and result.get("auto_rescheduled")
            ):
                continue

            event = result.get("event", {})
            requested = self._format_schedule(
                result.get("requested_start"), result.get("requested_end")
            )
            scheduled = self._format_schedule(event.get("start"), event.get("end"))
            name = str(email.get("sender_name") or "").strip()
            greeting = f"Hola {name}," if name else "Hola,"
            body = (
                f"{greeting}\n\n"
                f"El horario solicitado ({requested}) no estaba disponible. "
                f"La reunión quedó agendada automáticamente para {scheduled}.\n\n"
                "Si el nuevo horario no te resulta conveniente, responde a este "
                "correo para coordinar otra alternativa.\n\n"
                "Saludos,\nUTPConsult"
            )
            try:
                sent = self.gmail.send_reply(email, body)
                notification = {
                    "status": "completed",
                    "message": "El remitente fue notificado del nuevo horario.",
                    "email": sent,
                }
            except Exception as exc:
                notification = {
                    "status": "failed",
                    "message": f"No se pudo notificar el cambio de horario: {exc}",
                }
            ai_result.setdefault("acciones", []).append(
                {
                    "accion": "notificar_cambio_horario",
                    "status": notification["status"],
                    "resultado": notification,
                }
            )

    @staticmethod
    def _format_schedule(start: Any, end: Any = None) -> str:
        def parse(value: Any) -> datetime:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo(settings.app_timezone))
            return parsed.astimezone(ZoneInfo(settings.app_timezone))

        start_at = parse(start)
        if end is None:
            return start_at.strftime("%d/%m/%Y a las %H:%M")
        end_at = parse(end)
        return (
            f"el {start_at:%d/%m/%Y}, de {start_at:%H:%M} "
            f"a {end_at:%H:%M} ({settings.app_timezone})"
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
        output_payload = {
            "tool_result": tool_result or {},
            "respuesta": ai_result.get("respuesta", ""),
            "usage": ai_result.get("usage", {}),
        }
        self.database.update_action_status(
            action_id,
            "completed" if completed else "failed",
            output_data=output_payload,
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
        self.database.update_action_status(
            action_id,
            "failed",
            output_data={"respuesta": f"Error al procesar el correo: {exc}"},
            error_message=str(exc),
        )
        self.database.update_gmail_message_status(message_id, "failed")
