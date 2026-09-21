"""PostgreSQL persistence for users, AI actions, and Gmail synchronization."""

from __future__ import annotations

import base64
import hashlib
import json
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
    scopes_json TEXT NOT NULL DEFAULT '[]',
    token_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gmail_sync_state (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    last_history_id TEXT,
    last_message_id TEXT,
    watch_expiration_at TIMESTAMPTZ,
    last_sync_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'not_configured'
        CHECK (status IN ('not_configured', 'watching', 'syncing', 'error')),
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gmail_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gmail_message_id TEXT NOT NULL,
    thread_id TEXT,
    history_id TEXT,
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
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
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
    """PostgreSQL repository for UTP Assistant."""

    def __init__(self, dsn: str, encryption_secret: str) -> None:
        self.dsn = dsn
        key = base64.urlsafe_b64encode(
            hashlib.sha256(encryption_secret.encode("utf-8")).digest()
        )
        self._cipher = Fernet(key)

    def initialize(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
            conn.commit()

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

    def save_google_access(
        self, user_id: int, access_token: str, scopes: tuple[str, ...]
    ) -> None:
        encrypted_token = self._cipher.encrypt(access_token.encode("utf-8"))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO oauth_credentials (
                        user_id, access_token_encrypted, scopes_json
                    ) VALUES (%s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET
                        access_token_encrypted = EXCLUDED.access_token_encrypted,
                        scopes_json = EXCLUDED.scopes_json,
                        updated_at = NOW()
                    """,
                    (user_id, encrypted_token, json.dumps(scopes)),
                )
                cur.execute(
                    """
                    INSERT INTO gmail_sync_state (user_id)
                    VALUES (%s)
                    ON CONFLICT(user_id) DO NOTHING
                    """,
                    (user_id,),
                )
            conn.commit()

    def create_action(
        self,
        user_id: int,
        action_type: str,
        service: str,
        title: str,
        input_data: dict[str, Any] | None = None,
    ) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO actions (
                        user_id, action_type, service, title, input_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        action_type,
                        service,
                        title,
                        json.dumps(input_data) if input_data else None,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row["id"])

    def list_recent_actions(
        self, user_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, service, status, created_at, completed_at
                    FROM actions
                    WHERE user_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def table_names(self) -> list[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename
                    """
                )
                rows = cur.fetchall()
        return [str(row["tablename"]) for row in rows]

    # ── Gmail sync state ────────────────────────────────────────────────

    def get_gmail_sync_state(self, user_id: int) -> dict[str, Any] | None:
        """Return the current Gmail sync state for a user, or None."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM gmail_sync_state WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def update_gmail_sync_state(
        self,
        user_id: int,
        *,
        last_history_id: str | None = None,
        last_message_id: str | None = None,
        watch_expiration_at: str | None = None,
        status: str | None = None,
        last_error: str | None = None,
    ) -> None:
        """Update specific fields in gmail_sync_state."""
        fields: list[str] = []
        values: list[Any] = []

        if last_history_id is not None:
            fields.append("last_history_id = %s")
            values.append(last_history_id)
        if last_message_id is not None:
            fields.append("last_message_id = %s")
            values.append(last_message_id)
        if watch_expiration_at is not None:
            fields.append("watch_expiration_at = %s")
            values.append(watch_expiration_at)
        if status is not None:
            fields.append("status = %s")
            values.append(status)
        if last_error is not None:
            fields.append("last_error = %s")
            values.append(last_error)

        if not fields:
            return

        fields.append("last_sync_at = NOW()")
        fields.append("updated_at = NOW()")
        values.append(user_id)

        sql = f"UPDATE gmail_sync_state SET {', '.join(fields)} WHERE user_id = %s"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()

    # ── Gmail message tracking ──────────────────────────────────────────

    def save_gmail_message(
        self,
        user_id: int,
        gmail_message_id: str,
        thread_id: str | None = None,
        history_id: str | None = None,
        sender: str | None = None,
        subject: str | None = None,
        received_at: str | None = None,
    ) -> int:
        """Insert a Gmail message record (or ignore if duplicate)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gmail_messages (
                        user_id, gmail_message_id, thread_id, history_id,
                        sender, subject, received_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(user_id, gmail_message_id) DO UPDATE SET
                        history_id = COALESCE(EXCLUDED.history_id, gmail_messages.history_id)
                    RETURNING id
                    """,
                    (
                        user_id, gmail_message_id, thread_id,
                        history_id, sender, subject, received_at,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row["id"])

    def update_gmail_message_status(
        self, message_db_id: int, status: str
    ) -> None:
        """Update the processing status of a tracked Gmail message."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                if status in ("processed", "failed"):
                    cur.execute(
                        "UPDATE gmail_messages SET status = %s, processed_at = NOW() WHERE id = %s",
                        (status, message_db_id),
                    )
                else:
                    cur.execute(
                        "UPDATE gmail_messages SET status = %s WHERE id = %s",
                        (status, message_db_id),
                    )
            conn.commit()

    def list_pending_gmail_messages(
        self, user_id: int, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return Gmail messages that still need processing."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM gmail_messages
                    WHERE user_id = %s AND status IN ('new', 'queued')
                    ORDER BY first_seen_at ASC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    # ── Action updates ──────────────────────────────────────────────────

    def update_action_status(
        self,
        action_id: int,
        status: str,
        output_data: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update an action's status and optional result/error."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                if status == "running":
                    cur.execute(
                        "UPDATE actions SET status = %s, started_at = NOW() WHERE id = %s",
                        (status, action_id),
                    )
                elif status in ("completed", "failed", "cancelled"):
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
                            json.dumps(output_data) if output_data else None,
                            error_message,
                            action_id,
                        ),
                    )
                else:
                    cur.execute(
                        "UPDATE actions SET status = %s WHERE id = %s",
                        (status, action_id),
                    )
            conn.commit()

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        """Return a user by primary key."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM users WHERE id = %s", (user_id,)
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def _connect(self) -> psycopg2.extensions.connection:
        """Open a new connection with dict-like rows."""
        conn = psycopg2.connect(
            self.dsn,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        return conn
