"""Main Streamlit entry point for UTP Assistant."""

from __future__ import annotations

import streamlit as st
from google.oauth2.credentials import Credentials

from config import GOOGLE_SCOPES, settings
from database import Database
from services.calendar.calendar_service import CalendarService
from services.gmail.gmail_service import GmailService
from view.home_view import render_home
from view.login_view import render_login


st.set_page_config(
    page_title="UTP Assistant",
    page_icon=":material/smart_toy:",
    layout="centered",
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

access_token = st.user.tokens.get("access")
if not access_token:
    st.error("Google no devolvió el token necesario para Gmail y Calendar.")
    st.stop()

database.save_google_access(user["id"], access_token, GOOGLE_SCOPES)

# Services are ready for the future UTPAssistant model. They are not polled yet.
credentials = Credentials(token=access_token, scopes=GOOGLE_SCOPES)
gmail = GmailService(credentials=credentials)
calendar = CalendarService(credentials=credentials)

render_home(user=user, database=database)
