"""Minimal Google Calendar client used by the assistant."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

from config import settings


class CalendarConflictError(ValueError):
    """The requested Calendar interval overlaps another event."""


class CalendarService:
    """List, create, reschedule and delete calendar events."""

    def __init__(self, credentials: Credentials, calendar_id: str | None = None) -> None:
        self.credentials = credentials
        self.calendar_id = calendar_id or settings.google_calendar_id
        self._service: Resource | None = None

    def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Return events in a time range, ordered by start time."""
        self._validate_range(time_min, time_max)
        response = self._api().events().list(
            calendarId=self.calendar_id,
            timeMin=self._iso(time_min),
            timeMax=self._iso(time_max),
            maxResults=min(max(max_results, 1), 50),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return [self._normalize(event) for event in response.get("items", [])]

    def create_event(
        self,
        title: str,
        description: str,
        start_datetime: datetime,
        end_datetime: datetime,
        attendees: list[str],
    ) -> dict[str, Any]:
        """Create an event when the requested slot is free."""
        self._ensure_available(start_datetime, end_datetime)
        event = self._api().events().insert(
            calendarId=self.calendar_id,
            body={
                "summary": title,
                "description": description,
                "start": {"dateTime": self._iso(start_datetime)},
                "end": {"dateTime": self._iso(end_datetime)},
                "attendees": [{"email": email} for email in attendees],
            },
            sendUpdates="all",
        ).execute()
        return self._normalize(event)

    def create_event_at_next_available(
        self,
        title: str,
        description: str,
        requested_start: datetime,
        requested_end: datetime,
        attendees: list[str],
    ) -> dict[str, Any]:
        """Create an event in the earliest free business-hours slot."""
        self._validate_range(requested_start, requested_end)
        duration = requested_end - requested_start
        slots = self._available_slots(requested_start, duration, limit=1)
        if not slots:
            raise ValueError(
                "No se encontró disponibilidad en los próximos días hábiles"
            )
        start, end = slots[0]
        return self.create_event(
            title=title,
            description=(
                f"{description}\n\nHorario reprogramado automáticamente por "
                "indisponibilidad del horario solicitado."
            ),
            start_datetime=start,
            end_datetime=end,
            attendees=attendees,
        )

    def reschedule_event(
        self,
        event_id: str,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> dict[str, Any]:
        """Move an event to a free time slot."""
        self._ensure_available(start_datetime, end_datetime, ignore_event_id=event_id)
        event = self._api().events().patch(
            calendarId=self.calendar_id,
            eventId=event_id,
            body={
                "start": {"dateTime": self._iso(start_datetime)},
                "end": {"dateTime": self._iso(end_datetime)},
            },
            sendUpdates="all",
        ).execute()
        return self._normalize(event)

    def delete_event(self, event_id: str) -> dict[str, str]:
        """Delete an event and notify its attendees."""
        self._api().events().delete(
            calendarId=self.calendar_id,
            eventId=event_id,
            sendUpdates="all",
        ).execute()
        return {"id": event_id}

    def _ensure_available(
        self,
        start: datetime,
        end: datetime,
        ignore_event_id: str | None = None,
    ) -> None:
        events = self.list_events(start, end, max_results=50)
        if any(event["id"] != ignore_event_id for event in events):
            raise CalendarConflictError("El horario solicitado no está disponible")

    def _available_slots(
        self,
        requested_start: datetime,
        duration: timedelta,
        limit: int,
    ) -> list[tuple[datetime, datetime]]:
        timezone = requested_start.tzinfo
        if timezone is None:
            raise ValueError("La fecha solicitada debe incluir zona horaria")

        days: list[datetime] = []
        cursor = requested_start.replace(hour=0, minute=0, second=0, microsecond=0)
        while len(days) < settings.calendar_alternative_days:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)

        search_start = days[0].replace(
            hour=settings.calendar_business_start, minute=0
        )
        search_end = days[-1].replace(hour=settings.calendar_business_end, minute=0)
        busy = [
            (
                self._event_datetime(event["start"], timezone),
                self._event_datetime(event["end"], timezone),
            )
            for event in self.list_events(search_start, search_end, max_results=50)
            if event.get("start") and event.get("end")
        ]

        step = timedelta(minutes=settings.calendar_slot_step_minutes)
        slots: list[tuple[datetime, datetime]] = []
        for day in days:
            candidate = datetime.combine(
                day.date(), time(settings.calendar_business_start), tzinfo=timezone
            )
            day_end = datetime.combine(
                day.date(), time(settings.calendar_business_end), tzinfo=timezone
            )
            while candidate + duration <= day_end:
                end = candidate + duration
                if candidate > requested_start and not any(
                    candidate < busy_end and end > busy_start
                    for busy_start, busy_end in busy
                ):
                    slots.append((candidate, end))
                    if len(slots) == limit:
                        return slots
                candidate += step
        return slots

    @staticmethod
    def _event_datetime(value: str, timezone: Any) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone)

    def _api(self) -> Resource:
        if self._service is None:
            self._service = build(
                "calendar", "v3", credentials=self.credentials, cache_discovery=False
            )
        return self._service

    @staticmethod
    def _validate_range(start: datetime, end: datetime) -> None:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Las fechas deben incluir zona horaria")
        if end <= start:
            raise ValueError("La fecha final debe ser posterior a la inicial")

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("La fecha debe incluir zona horaria")
        return value.isoformat()

    @staticmethod
    def _normalize(event: dict[str, Any]) -> dict[str, Any]:
        start, end = event.get("start", {}), event.get("end", {})
        return {
            "id": event.get("id", ""),
            "title": event.get("summary", ""),
            "description": event.get("description", ""),
            "start": start.get("dateTime", start.get("date", "")),
            "end": end.get("dateTime", end.get("date", "")),
            "attendees": [item.get("email", "") for item in event.get("attendees", [])],
            "html_link": event.get("htmlLink", ""),
        }
