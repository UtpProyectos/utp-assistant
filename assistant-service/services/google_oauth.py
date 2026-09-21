"""Google OAuth helpers for long-lived Gmail and Calendar access."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleOAuthError(RuntimeError):
    """Raised when the offline Google authorization cannot be completed."""


class GoogleOAuthService:
    """Create and refresh credentials that include a Google refresh token."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        state_secret: str,
        scopes: tuple[str, ...],
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.state_secret = state_secret.encode("utf-8")
        self.scopes = scopes

    def authorization_url(self, google_sub: str, login_hint: str | None = None) -> str:
        """Return a consent URL that explicitly requests offline access."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "access_type": "offline",
            # Google may omit refresh_token after the first grant unless consent
            # is requested again.
            "prompt": "consent",
            "state": self._create_state(google_sub),
        }
        if login_hint:
            params["login_hint"] = login_hint
        return f"{GOOGLE_AUTHORIZATION_URL}?{urlencode(params)}"

    def exchange_code(
        self,
        code: str,
        state: str,
        expected_google_sub: str,
    ) -> dict[str, Any]:
        """Exchange Google's callback code and validate that it belongs to the user."""
        state_google_sub = self._verify_state(state)
        if not hmac.compare_digest(state_google_sub, expected_google_sub):
            raise GoogleOAuthError("La autorización no corresponde al usuario activo.")

        try:
            response = requests.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleOAuthError("No se pudo contactar a Google para obtener el token.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleOAuthError("Google devolvió una respuesta OAuth inválida.") from exc

        if not response.ok:
            description = payload.get("error_description") or payload.get("error")
            raise GoogleOAuthError(f"Google rechazó la autorización: {description}")

        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not access_token:
            raise GoogleOAuthError("Google no devolvió un access_token válido.")
        if not refresh_token:
            raise GoogleOAuthError(
                "Google no devolvió refresh_token. Revoca el acceso previo de la app "
                "en tu cuenta de Google y vuelve a autorizar."
            )

        expires_in = int(payload.get("expires_in", 3600))
        return {
            "access_token": str(access_token),
            "refresh_token": str(refresh_token),
            "expiry": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            "scopes": tuple(payload.get("scope", "").split()) or self.scopes,
        }

    def credentials_from_record(self, record: dict[str, Any]) -> Credentials:
        """Rebuild complete refreshable Google credentials from encrypted storage."""
        expiry = record.get("expiry")
        # PostgreSQL TIMESTAMPTZ values are timezone-aware, while google-auth
        # 2.x still compares expiry against a naive UTC datetime internally.
        if isinstance(expiry, datetime) and expiry.tzinfo is not None:
            expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

        return Credentials(
            token=record.get("access_token"),
            refresh_token=record["refresh_token"],
            token_uri=GOOGLE_TOKEN_URL,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=list(record.get("scopes") or self.scopes),
            expiry=expiry,
        )

    @staticmethod
    def refresh(credentials: Credentials) -> None:
        """Refresh an expired/invalid access token before calling Google APIs."""
        credentials.refresh(Request())

    def _create_state(self, google_sub: str) -> str:
        payload = {
            "sub": google_sub,
            "exp": int(time.time()) + 600,
            "nonce": secrets.token_urlsafe(16),
        }
        body = self._b64encode(json.dumps(payload, separators=(",", ":")).encode())
        signature = hmac.new(self.state_secret, body.encode(), hashlib.sha256).digest()
        return f"{body}.{self._b64encode(signature)}"

    def _verify_state(self, state: str) -> str:
        try:
            body, supplied_signature = state.split(".", 1)
            expected_signature = hmac.new(
                self.state_secret, body.encode(), hashlib.sha256
            ).digest()
            if not hmac.compare_digest(
                self._b64decode(supplied_signature), expected_signature
            ):
                raise ValueError("invalid signature")
            payload = json.loads(self._b64decode(body))
            if int(payload["exp"]) < int(time.time()):
                raise ValueError("expired state")
            return str(payload["sub"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GoogleOAuthError(
                "La solicitud de autorización expiró o no es válida. Inténtalo otra vez."
            ) from exc

    @staticmethod
    def _b64encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
