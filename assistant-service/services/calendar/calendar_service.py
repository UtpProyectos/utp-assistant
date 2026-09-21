"""Minimal Google Calendar client used by the assistant."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

from config import settings


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
            raise ValueError("El horario solicitado no está disponible")

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
