"""Small shared configuration for the Assistant service."""

from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()

GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
)


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL") or os.getenv(
            "UTP_DATABASE_PATH",
            "postgresql://postgres:postgres@localhost:5432/utp_assistant",
        )
        self.google_calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")


settings = Settings()
