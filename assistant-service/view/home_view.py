"""Welcome dashboard view shown after Google login."""

from __future__ import annotations

from typing import Any

import streamlit as st

from database import Database


HOME_CSS = """
<style>
/* Modern Shadcn UI Tokens */
.stat-card {
    background: rgba(24, 24, 27, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 1.1rem 1.25rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.stat-label {
    font-size: 0.8rem;
    color: #a1a1aa;
    font-weight: 500;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.stat-value {
    font-size: 1.45rem;
    font-weight: 700;
    color: #f4f4f5;
}
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.85rem;
    font-weight: 500;
}
.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #22c55e;
    box-shadow: 0 0 8px #22c55e;
}
.empty-card {
    border: 1px dashed rgba(255, 255, 255, 0.15);
    border-radius: 12px;
    padding: 2.5rem;
    text-align: center;
    background: rgba(24, 24, 27, 0.25);
    margin-top: 1rem;
}
.sidebar-profile {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 1.2rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.avatar-img {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: 2px solid rgba(255, 255, 255, 0.15);
    object-fit: cover;
}
.avatar-fallback {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: #0057B8;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 1.1rem;
}
</style>
"""


def render_home(user: dict[str, Any], database: Database) -> None:
    st.markdown(HOME_CSS, unsafe_allow_html=True)

    # ── Sidebar Profile & Controls ──────────────────────────────────────
    with st.sidebar:
        pic = user.get("picture_url")
        name = user.get("name") or "Usuario"
        email = user.get("email") or ""
        first_letter = name[0].upper() if name else "U"

        if pic:
            avatar_html = f'<img src="{pic}" class="avatar-img" alt="{name}">'
        else:
            avatar_html = f'<div class="avatar-fallback">{first_letter}</div>'

        st.markdown(
            f"""
            <div class="sidebar-profile">
                {avatar_html}
                <div style="overflow: hidden;">
                    <div style="font-weight: 600; font-size: 0.95rem; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{name}</div>
                    <div style="color: #a1a1aa; font-size: 0.8rem; white-space: nowrap; text-overflow: ellipsis; overflow: hidden;">{email}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption("UTP Assistant • v0.1")
        if st.button("Cerrar sesión", icon=":material/logout:", use_container_width=True):
            st.logout()

    # ── Dashboard Header ───────────────────────────────────────────────
    st.title("Bienvenido a UTP Assistant 👋")
    st.markdown(
        "<p style='color: #a1a1aa; font-size: 1.05rem; margin-bottom: 1.8rem;'>"
        "Tu asistente está conectado y listo para coordinar correos, reuniones y tareas."
        "</p>",
        unsafe_allow_html=True,
    )

    # ── Quick KPI / Status Cards ───────────────────────────────────────
    activities = database.list_recent_actions(user_id=user["id"], limit=10)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="stat-card">
                <div class="stat-label">Estado Asistente</div>
                <div class="status-pill">
                    <span class="status-dot"></span>
                    <span class="stat-value" style="font-size: 1.15rem;">Escuchando</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="stat-card">
                <div class="stat-label">Servicios Activos</div>
                <div class="stat-value" style="font-size: 1.15rem;">Gmail + Calendar</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Acciones Totales</div>
                <div class="stat-value">{len(activities)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Recent Activities ──────────────────────────────────────────────
    st.subheader("Últimas actividades", icon=":material/history:")

    if activities:
        st.dataframe(
            activities,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": None,
                "title": st.column_config.TextColumn("Actividad", width="large"),
                "service": st.column_config.TextColumn("Servicio", width="small"),
                "status": st.column_config.TextColumn("Estado", width="small"),
                "created_at": st.column_config.DatetimeColumn("Fecha de Registro", format="YYYY-MM-DD HH:mm"),
                "completed_at": st.column_config.DatetimeColumn("Finalizado", format="YYYY-MM-DD HH:mm"),
            },
        )
    else:
        st.markdown(
            """
            <div class="empty-card">
                <div style="font-size: 2rem; margin-bottom: 0.6rem;">📬</div>
                <h4 style="margin: 0 0 0.3rem 0; font-weight: 600;">Aún no hay actividades registradas</h4>
                <p style="color: #a1a1aa; font-size: 0.9rem; margin: 0;">
                    Cuando el modelo de IA procese correos entrantes o cree eventos, el historial aparecerá aquí en tiempo real.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

