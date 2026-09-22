"""Main Streamlit entry point for the current UTP Assistant MVP."""

from __future__ import annotations

import streamlit as st
from google.auth.exceptions import GoogleAuthError

from config import GOOGLE_SCOPES, settings
from database import Database
from model.assistant import UTPAssistant
from services.calendar.calendar_service import CalendarService
from services.gmail.email_poller import EmailPollingService
from services.gmail.gmail_service import GmailService
from services.google_oauth import GoogleOAuthError, GoogleOAuthService
from services.jira.jira_service import JiraService
from view.home_view import render_home
from view.login_view import render_google_authorization, render_login


st.set_page_config(
    page_title="UTP Assistant",
    page_icon=":material/smart_toy:",
    layout="wide",
)


@st.cache_resource
def get_database() -> Database:
    cookie_secret = str(st.secrets["auth"]["cookie_secret"])
    database = Database(settings.database_url, encryption_secret=cookie_secret)
    database.initialize()
    return database


database = get_database()

if not st.user.is_logged_in:
    render_login()
    st.stop()

user = database.save_user(
    google_sub=str(st.user["sub"]),
    email=str(st.user["email"]),
    name=str(st.user.get("name") or st.user["email"]),
    picture_url=str(st.user.get("picture") or "") or None,
)

auth_config = st.secrets["auth"]
offline_redirect_uri = str(
    auth_config.get("offline_redirect_uri")
    or str(auth_config["redirect_uri"]).removesuffix("oauth2callback")
)
google_oauth = GoogleOAuthService(
    client_id=str(auth_config["client_id"]),
    client_secret=str(auth_config["client_secret"]),
    redirect_uri=offline_redirect_uri,
    state_secret=str(auth_config["cookie_secret"]),
    scopes=GOOGLE_SCOPES,
)

# Streamlit intentionally exposes only ID/access tokens. Google returns the
# refresh token through this separate offline-consent callback so it can be
# encrypted in PostgreSQL and reused after the access token expires.
oauth_code = st.query_params.get("code")
oauth_state = st.query_params.get("state")
oauth_provider_error = st.query_params.get("error")
if oauth_provider_error:
    description = st.query_params.get("error_description") or oauth_provider_error
    st.session_state["google_oauth_error"] = f"Google rechazó la autorización: {description}"
    st.query_params.clear()
    st.rerun()

if oauth_code or oauth_state:
    try:
        if not oauth_code or not oauth_state:
            raise GoogleOAuthError("El callback de Google está incompleto.")
        token_data = google_oauth.exchange_code(
            code=str(oauth_code),
            state=str(oauth_state),
            expected_google_sub=str(st.user["sub"]),
        )
        database.save_google_credentials(
            user_id=user["id"],
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            scopes=token_data["scopes"],
            expiry=token_data["expiry"],
        )
        st.session_state.pop("google_oauth_error", None)
    except GoogleOAuthError as exc:
        st.session_state["google_oauth_error"] = str(exc)
    st.query_params.clear()
    st.rerun()

authorization_url = google_oauth.authorization_url(
    str(st.user["sub"]),
    login_hint=str(st.user["email"]),
)
stored_credentials = database.get_google_credentials(user["id"])
if not stored_credentials:
    render_google_authorization(
        authorization_url,
        st.session_state.pop("google_oauth_error", None),
    )
    st.stop()

# Gmail and Calendar share one complete, refreshable credential set.
credentials = google_oauth.credentials_from_record(stored_credentials)
if not credentials.valid:
    try:
        google_oauth.refresh(credentials)
        database.save_google_credentials(
            user_id=user["id"],
            access_token=str(credentials.token),
            refresh_token=credentials.refresh_token,
            scopes=tuple(credentials.scopes or GOOGLE_SCOPES),
            expiry=credentials.expiry,
        )
    except GoogleAuthError as exc:
        render_google_authorization(
            authorization_url,
            "La autorización guardada ya no es válida. Autoriza nuevamente "
            f"Gmail y Calendar. ({exc})",
        )
        st.stop()

gmail = GmailService(credentials=credentials)
calendar = CalendarService(
    credentials=credentials,
    calendar_id=settings.google_calendar_id,
)
jira = JiraService()

try:
    assistant = UTPAssistant(calendar_service=calendar, jira_service=jira)
except ValueError as exc:
    st.error(f"Configuración del modelo incompleta: {exc}")
    render_home(user=user, database=database, poll_info=None)
    st.stop()

poller = EmailPollingService(
    gmail_service=gmail,
    assistant=assistant,
    database=database,
    user_id=user["id"],
)


@st.fragment(run_every=settings.gmail_poll_seconds)
def poll_gmail() -> None:
    """Check Gmail periodically while this Streamlit session is active."""
    try:
        result = poller.process_new_emails()
        st.session_state["last_poll"] = result
        st.session_state["last_poll_error"] = None

        # Refresh the dashboard when something was actually processed.
        if result["processed"] or result["failed"]:
            st.rerun()
    except Exception as exc:  # Keep the UI alive if Google/LLM has a temporary error.
        st.session_state["last_poll_error"] = str(exc)


poll_gmail()

poll_info = {
    "result": st.session_state.get("last_poll"),
    "error": st.session_state.get("last_poll_error"),
    "seconds": settings.gmail_poll_seconds,
    "query": settings.gmail_query,
}
render_home(user=user, database=database, poll_info=poll_info)
