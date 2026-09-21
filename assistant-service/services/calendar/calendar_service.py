"""Small, reusable wrapper around the Google Calendar API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

from config import settings


class CalendarService:
    """Expose Calendar operations without coupling them to FastAPI or AI logic."""

    def __init__(
        self,
        credentials: Credentials | None = None,
        calendar_id: str | None = None,
    ) -> None:
        self.credentials = credentials
        self.calendar_id = calendar_id or settings.google_calendar_id
        self._service: Resource | None = None

    def authenticate(self) -> Resource:
        """Authenticate and return the Google Calendar API client."""
        if self._service is None:
            if self.credentials is None:
                raise ValueError("Google credentials are required")
            self._service = build(
                "calendar", "v3", credentials=self.credentials, cache_discovery=False
            )
        return self._service

    def list_events(
        self,
        max_results: int = 20,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return normalized events ordered by their start time."""
        params: dict[str, Any] = {
            "calendarId": self.calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
            "timeMin": self._iso(time_min or datetime.now().astimezone()),
        }
        if time_max:
            params["timeMax"] = self._iso(time_max)
        response = self.authenticate().events().list(**params).execute()
        return [self._normalize_event(event) for event in response.get("items", [])]

    def check_availability(
        self, start_datetime: datetime, end_datetime: datetime
    ) -> bool:
        """Return True when the configured calendar has no busy period."""
        self._validate_range(start_datetime, end_datetime)
        response = (
            self.authenticate()
            .freebusy()
            .query(
                body={
                    "timeMin": self._iso(start_datetime),
                    "timeMax": self._iso(end_datetime),
                    "items": [{"id": self.calendar_id}],
                }
            )
            .execute()
        )
        busy = response.get("calendars", {}).get(self.calendar_id, {}).get("busy", [])
        return len(busy) == 0

    def create_event(
        self,
        title: str,
        description: str,
        start_datetime: datetime,
        end_datetime: datetime,
        attendees: list[str],
    ) -> dict[str, Any]:
        """Create an event after rejecting overlapping time slots."""
        self._validate_range(start_datetime, end_datetime)
        if not self.check_availability(start_datetime, end_datetime):
            raise ValueError("The requested time slot is not available")

        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": self._iso(start_datetime)},
            "end": {"dateTime": self._iso(end_datetime)},
            "attendees": [{"email": email} for email in attendees],
        }
        event = (
            self.authenticate()
            .events()
            .insert(calendarId=self.calendar_id, body=body, sendUpdates="all")
            .execute()
        )
        return self._normalize_event(event)

    def get_event(self, event_id: str) -> dict[str, Any]:
        """Return a single calendar event by its ID."""
        event = (
            self.authenticate()
            .events()
            .get(calendarId=self.calendar_id, eventId=event_id)
            .execute()
        )
        return self._normalize_event(event)

    def update_event(
        self,
        event_id: str,
        title: str | None = None,
        description: str | None = None,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Patch an existing event with the provided fields."""
        body: dict[str, Any] = {}
        if title is not None:
            body["summary"] = title
        if description is not None:
            body["description"] = description
        if start_datetime is not None:
            body["start"] = {"dateTime": self._iso(start_datetime)}
        if end_datetime is not None:
            body["end"] = {"dateTime": self._iso(end_datetime)}
        if attendees is not None:
            body["attendees"] = [{"email": email} for email in attendees]

        event = (
            self.authenticate()
            .events()
            .patch(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=body,
                sendUpdates="all",
            )
            .execute()
        )
        return self._normalize_event(event)

    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event. Returns True on success."""
        self.authenticate().events().delete(
            calendarId=self.calendar_id,
            eventId=event_id,
            sendUpdates="all",
        ).execute()
        return True

    @staticmethod
    def _validate_range(start_datetime: datetime, end_datetime: datetime) -> None:
        if start_datetime.tzinfo is None or end_datetime.tzinfo is None:
            raise ValueError("Start and end datetimes must include a timezone")
        if end_datetime <= start_datetime:
            raise ValueError("End datetime must be after start datetime")

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("Datetime must include a timezone")
        return value.isoformat()

    @staticmethod
    def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": event.get("id", ""),
            "title": event.get("summary", ""),
            "description": event.get("description", ""),
            "start": event.get("start", {}).get(
                "dateTime", event.get("start", {}).get("date", "")
            ),
            "end": event.get("end", {}).get(
                "dateTime", event.get("end", {}).get("date", "")
            ),
            "attendees": [
                attendee.get("email", "") for attendee in event.get("attendees", [])
            ],
            "html_link": event.get("htmlLink", ""),
        }
