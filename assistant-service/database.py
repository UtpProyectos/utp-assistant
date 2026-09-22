"""PostgreSQL persistence for UTP Assistant operational state."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
from cryptography.fernet import Fernet


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    google_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    picture_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_credentials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'google',
    access_token_encrypted BYTEA,
    refresh_token_encrypted BYTEA,
    token_expires_at TIMESTAMPTZ,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE oauth_credentials
    ADD COLUMN IF NOT EXISTS refresh_token_encrypted BYTEA;
ALTER TABLE oauth_credentials
    ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS gmail_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gmail_message_id TEXT NOT NULL,
    thread_id TEXT,
    sender TEXT,
    subject TEXT,
    received_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'queued', 'processed', 'ignored', 'failed')),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    UNIQUE (user_id, gmail_message_id)
);

CREATE TABLE IF NOT EXISTS actions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gmail_message_id INTEGER REFERENCES gmail_messages(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL,
    service TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'failed')),
    input_json TEXT,
    output_json TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_actions_user_created
    ON actions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gmail_messages_user_status
    ON gmail_messages(user_id, status);
"""


class Database:
    """Small PostgreSQL repository used by the Assistant service."""

    def __init__(self, dsn: str, encryption_secret: str) -> None:
        self.dsn = dsn
        key = base64.urlsafe_b64encode(
            hashlib.sha256(encryption_secret.encode("utf-8")).digest()
        )
        self._cipher = Fernet(key)

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
            conn.commit()

    # ── Users / Google session ────────────────────────────────────────

    def save_user(
        self,
        google_sub: str,
        email: str,
        name: str,
        picture_url: str | None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (google_sub, email, name, picture_url)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(google_sub) DO UPDATE SET
                        email = EXCLUDED.email,
                        name = EXCLUDED.name,
                        picture_url = EXCLUDED.picture_url,
                        is_active = TRUE,
                        last_login_at = NOW()
                    RETURNING *
                    """,
                    (google_sub, email, name, picture_url),
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row)

    def save_google_credentials(
        self,
        user_id: int,
        access_token: str,
        refresh_token: str | None,
        scopes: tuple[str, ...],
        expiry: Any,
    ) -> None:
        # google-auth returns a naive datetime representing UTC after a token
        # refresh. Make it explicit before writing to PostgreSQL TIMESTAMPTZ.
        if isinstance(expiry, datetime) and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        encrypted_token = self._cipher.encrypt(access_token.encode("utf-8"))
        encrypted_refresh = (
            self._cipher.encrypt(refresh_token.encode("utf-8"))
            if refresh_token
            else None
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO oauth_credentials (
                        user_id, access_token_encrypted, refresh_token_encrypted,
                        scopes_json, token_expires_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET
                        access_token_encrypted = EXCLUDED.access_token_encrypted,
                        refresh_token_encrypted = COALESCE(
                            EXCLUDED.refresh_token_encrypted,
                            oauth_credentials.refresh_token_encrypted
                        ),
                        scopes_json = EXCLUDED.scopes_json,
                        token_expires_at = EXCLUDED.token_expires_at,
                        updated_at = NOW()
                    """,
                    (
                        user_id,
                        encrypted_token,
                        encrypted_refresh,
                        json.dumps(scopes),
                        expiry,
                    ),
                )
            conn.commit()

    def get_google_credentials(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT access_token_encrypted, refresh_token_encrypted,
                           scopes_json, token_expires_at
                    FROM oauth_credentials
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()

        if not row or not row["refresh_token_encrypted"]:
            return None

        def decrypt(value: Any) -> str | None:
            if value is None:
                return None
            raw = bytes(value) if isinstance(value, memoryview) else value
            return self._cipher.decrypt(raw).decode("utf-8")

        return {
            "access_token": decrypt(row["access_token_encrypted"]),
            "refresh_token": decrypt(row["refresh_token_encrypted"]),
            "scopes": tuple(json.loads(row["scopes_json"] or "[]")),
            "expiry": row["token_expires_at"],
        }

    # ── Gmail message idempotency ────────────────────────────────────

    def get_gmail_message_by_gmail_id(
        self,
        user_id: int,
        gmail_message_id: str,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM gmail_messages
                    WHERE user_id = %s AND gmail_message_id = %s
                    """,
                    (user_id, gmail_message_id),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def save_gmail_message(
        self,
        user_id: int,
        gmail_message_id: str,
        thread_id: str | None = None,
        sender: str | None = None,
        subject: str | None = None,
        received_at: str | None = None,
    ) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gmail_messages (
                        user_id, gmail_message_id, thread_id,
                        sender, subject, received_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(user_id, gmail_message_id) DO UPDATE SET
                        thread_id = COALESCE(EXCLUDED.thread_id, gmail_messages.thread_id),
                        sender = COALESCE(EXCLUDED.sender, gmail_messages.sender),
                        subject = COALESCE(EXCLUDED.subject, gmail_messages.subject)
                    RETURNING id
                    """,
                    (
                        user_id,
                        gmail_message_id,
                        thread_id,
                        sender,
                        subject,
                        received_at,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])

    def update_gmail_message_status(self, message_db_id: int, status: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if status in ("processed", "failed"):
                    cur.execute(
                        """
                        UPDATE gmail_messages
                        SET status = %s, processed_at = NOW()
                        WHERE id = %s
                        """,
                        (status, message_db_id),
                    )
                else:
                    cur.execute(
                        "UPDATE gmail_messages SET status = %s WHERE id = %s",
                        (status, message_db_id),
                    )
            conn.commit()

    # ── Actions displayed in the Assistant UI ────────────────────────

    def create_action(
        self,
        user_id: int,
        action_type: str,
        service: str,
        title: str,
        input_data: dict[str, Any] | None = None,
        gmail_message_db_id: int | None = None,
    ) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO actions (
                        user_id, gmail_message_id, action_type,
                        service, title, input_json
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        gmail_message_db_id,
                        action_type,
                        service,
                        title,
                        json.dumps(input_data, ensure_ascii=False)
                        if input_data
                        else None,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])

    def update_action_status(
        self,
        action_id: int,
        status: str,
        output_data: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE actions SET
                        status = %s,
                        output_json = %s,
                        error_message = %s,
                        completed_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        status,
                        json.dumps(output_data, ensure_ascii=False, default=str)
                        if output_data
                        else None,
                        error_message,
                        action_id,
                    ),
                )
            conn.commit()

    def list_recent_actions(
        self,
        user_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, service, status, created_at, completed_at,
                           output_json, error_message, action_type
                    FROM actions
                    WHERE user_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cur.fetchall()
        activities = []
        for row in rows:
            activity = dict(row)
            raw_output = activity.pop("output_json", None)
            try:
                activity["output_data"] = json.loads(raw_output) if raw_output else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                activity["output_data"] = {}
            activities.append(activity)
        return activities

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(
            self.dsn,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
