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
    "jira": "Jira",
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


def _render_activity_detail(activity: dict[str, Any]) -> None:
    """Show the stored model response and tool result for one action."""
    output = activity.get("output_data")
    output = output if isinstance(output, dict) else {}
    response = str(output.get("respuesta") or "").strip()
    tool_result = output.get("tool_result")
    usage = output.get("usage")
    error = str(activity.get("error_message") or "").strip()

    with st.container(border=True):
        st.subheader("Detalle de la acción", icon=":material/chat_info:")
        st.caption(str(activity.get("title") or "Actividad sin título"))
        if response:
            st.markdown(response)
        else:
            st.info("Esta acción no tiene una respuesta del modelo almacenada.")
        if error:
            st.error(error)
        if tool_result or usage:
            with st.expander("Resultado técnico"):
                if tool_result:
                    st.json(tool_result)
                if usage:
                    st.caption(
                        "Tokens: "
                        f"{int(usage.get('prompt_tokens', 0) or 0)} entrada · "
                        f"{int(usage.get('completion_tokens', 0) or 0)} salida · "
                        f"{int(usage.get('total_tokens', 0) or 0)} total"
                    )


def render_home(
    user: dict[str, Any],
    database: Database,
    poll_info: dict[str, Any] | None = None,
) -> None:
    """Render the operational Gmail, Calendar, and Jira dashboard."""
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
            [
                ("Gmail", "secondary"),
                ("Calendar", "secondary"),
                ("Jira", "secondary"),
            ],
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
        f"Hola, {name}. Gmail se revisa automáticamente; Calendar y Jira ejecutan "
        "solo las acciones confirmadas por el modelo."
    )
    ui.badges(
        [
            (state_label, "destructive" if poll_error else "default"),
            ("OAuth offline", "outline"),
            ("Gmail + Calendar + Jira", "secondary"),
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

    overview_columns = st.columns([1.2, 1, 1], gap="medium")
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
    with overview_columns[2]:
        ui.card(
            title="Integración de Jira",
            description="Registra trabajo confirmado a partir de correos y adjuntos.",
            content="Puede crear Historias y Tareas con trazabilidad al mensaje original.",
            footer="Credenciales administradas por el entorno del Assistant.",
            key="jira-integration-card",
        )

    st.subheader("Actividad reciente", icon=":material/history:")
    st.caption(
        "Decisiones del modelo y acciones ejecutadas por Gmail, Calendar o Jira."
    )

    if activities:
        st.caption("Selecciona una acción para ver la respuesta entregada por la IA.")
        selection = st.dataframe(
            _activity_rows(activities),
            column_order=("activity", "service", "status", "created_at"),
            column_config={
                "activity": st.column_config.TextColumn("Actividad", width="large"),
                "service": st.column_config.TextColumn("Servicio", width="small"),
                "status": st.column_config.TextColumn("Estado", width="small"),
                "created_at": st.column_config.TextColumn("Fecha", width="medium"),
            },
            hide_index=True,
            height="content",
            on_select="rerun",
            selection_mode="single-row",
            key="recent-activity-table",
            lazy=False,
        )
        if selection.selection.rows:
            _render_activity_detail(activities[selection.selection.rows[0]])
    else:
        ui.card(
            title="Sin actividad todavía",
            description="El historial aparecerá aquí cuando llegue un correo compatible con el filtro.",
            content=(
                "El monitor está listo para analizar mensajes, coordinar reuniones "
                "y crear tickets."
            ),
            footer="La bandeja se revisa automáticamente.",
            key="empty-activity-card",
        )
