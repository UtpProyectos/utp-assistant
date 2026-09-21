"""Shared configuration for UTP Assistant."""

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
        # Persistence used by the Assistant UI and polling state.
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/utp_assistant",
        )

        # Google.
        self.google_calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

        # LLM provider. During development OpenRouter can be used, then switched
        # to OpenAI without changing the model code.
        self.llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        self.llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1000"))

        # Poll unread Inbox messages received recently. The time window prevents
        # a first login from processing an entire historical unread backlog.
        self.gmail_poll_seconds = int(os.getenv("GMAIL_POLL_SECONDS", "60"))
        self.gmail_max_results = int(os.getenv("GMAIL_MAX_RESULTS", "10"))
        self.gmail_query = os.getenv(
            "GMAIL_QUERY",
            "is:unread in:inbox newer_than:2d",
        )

        # Dates without an explicit offset are interpreted in this timezone.
        self.app_timezone = os.getenv("APP_TIMEZONE", "America/Lima")


settings = Settings()
