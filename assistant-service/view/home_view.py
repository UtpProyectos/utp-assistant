"""Shadcn dashboard shown after Google authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st
import streamlit_shadcn_ui as ui

from database import Database


STATUS_LABELS = {
    "pending": "Pendiente",
    "completed": "Completada",
    "failed": "Fallida",
}
SERVICE_LABELS = {
    "assistant": "Asistente",
    "calendar": "Calendar",
    "gmail": "Gmail",
}


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone().strftime("%d/%m/%Y %H:%M")
    return "—" if value is None else str(value)


def _activity_rows(activities: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "activity": str(activity.get("title") or "Actividad sin título"),
            "service": SERVICE_LABELS.get(
                str(activity.get("service")),
                str(activity.get("service") or "—").title(),
            ),
            "status": STATUS_LABELS.get(
                str(activity.get("status")),
                str(activity.get("status") or "—").title(),
            ),
            "created_at": _format_datetime(activity.get("created_at")),
        }
        for activity in activities
    ]


def render_home(
    user: dict[str, Any],
    database: Database,
    poll_info: dict[str, Any] | None = None,
) -> None:
    """Render the operational Gmail and Calendar dashboard."""
    name = str(user.get("name") or "Usuario")
    email = str(user.get("email") or "")
    picture = str(user.get("picture_url") or "") or None
    initials = "".join(part[0] for part in name.split()[:2]).upper() or "U"

    with st.sidebar:
        ui.avatar(
            src=picture,
            fallback=initials,
            alt=f"Foto de {name}",
            size="lg",
            key="sidebar-avatar",
        )
        st.subheader(name)
        st.caption(email)
        ui.badges(
            [("Gmail", "secondary"), ("Calendar", "secondary")],
            key="sidebar-services",
        )
        ui.separator(key="sidebar-separator")
        st.caption("UTP Assistant · v0.1")
        if ui.button(
            "Cerrar sesión",
            key="logout-button",
            variant="outline",
            width="stretch",
        ):
            st.logout()

    activities = database.list_recent_actions(user_id=user["id"], limit=10)
    poll_info = poll_info or {}
    poll_error = poll_info.get("error")
    poll_result = poll_info.get("result") or {}
    poll_seconds = int(poll_info.get("seconds", 60))
    query = str(poll_info.get("query") or "")

    found = int(poll_result.get("found", 0))
    processed = int(poll_result.get("processed", 0))
    skipped = int(poll_result.get("skipped", 0))
    failed = int(poll_result.get("failed", 0))
    actions_completed = int(poll_result.get("actions_completed", 0))
    actions_failed = int(poll_result.get("actions_failed", 0))
    state_label = "Requiere atención" if poll_error else "En escucha"

    st.title("Panel del asistente", icon=":material/smart_toy:")
    st.caption(
        f"Hola, {name}. Gmail se revisa automáticamente y Calendar ejecuta "
        "solo las acciones confirmadas por el modelo."
    )
    ui.badges(
        [
            (state_label, "destructive" if poll_error else "default"),
            ("OAuth offline", "outline"),
            ("Gmail + Calendar", "secondary"),
        ],
        key="system-status-badges",
    )

    metric_columns = st.columns(4, gap="small")
    with metric_columns[0]:
        ui.metric_card(
            "Estado",
            state_label,
            description="Monitor de correo activo" if not poll_error else "Revisa el detalle",
            variant="dashboard",
            key="metric-status",
        )
    with metric_columns[1]:
        ui.metric_card(
            "Encontrados",
            found,
            description="Correos del último ciclo",
            variant="dashboard",
            key="metric-found",
        )
    with metric_columns[2]:
        ui.metric_card(
            "Procesados",
            processed,
            description=f"{failed} fallidos · {skipped} omitidos",
            variant="dashboard",
            key="metric-processed",
        )
    with metric_columns[3]:
        ui.metric_card(
            "Frecuencia",
            f"{poll_seconds}s",
            description="Próxima revisión automática",
            variant="dashboard",
            key="metric-frequency",
        )

    if poll_error:
        ui.alert(
            "La última revisión de Gmail falló",
            str(poll_error),
            variant="destructive",
            key="poll-error-alert",
        )

    overview_columns = st.columns([1.35, 1], gap="medium")
    with overview_columns[0]:
        ui.card(
            title="Monitor de Gmail",
            description="Búsqueda activa de mensajes nuevos que debe evaluar el modelo.",
            content=(
                f"{found} encontrados · {processed} procesados · "
                f"{skipped} omitidos · {failed} fallidos"
            ),
            footer=f"Filtro: {query}" if query else "Filtro no configurado",
            key="gmail-monitor-card",
        )
    with overview_columns[1]:
        ui.card(
            title="Integración de Calendar",
            description="Opera con las mismas credenciales OAuth renovables.",
            content="Puede leer, crear, reagendar y eliminar reuniones.",
            footer=f"{actions_completed} acciones completadas · {actions_failed} fallidas",
            key="calendar-integration-card",
        )

    st.subheader("Actividad reciente", icon=":material/history:")
    st.caption("Decisiones del modelo y acciones ejecutadas por Gmail o Calendar.")

    if activities:
        ui.table(
            _activity_rows(activities),
            columns=[
                {"key": "activity", "label": "Actividad"},
                {"key": "service", "label": "Servicio"},
                {"key": "status", "label": "Estado"},
                {"key": "created_at", "label": "Fecha"},
            ],
            caption="Las 10 acciones más recientes",
            max_height=440,
            key="recent-activity-table",
        )
    else:
        ui.card(
            title="Sin actividad todavía",
            description="El historial aparecerá aquí cuando llegue un correo compatible con el filtro.",
            content="El monitor está listo para analizar mensajes y coordinar reuniones.",
            footer="La bandeja se revisa automáticamente.",
            key="empty-activity-card",
        )
