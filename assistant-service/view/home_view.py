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


def _email_activity_rows(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "subject": str(group.get("subject") or "Correo sin asunto"),
            "sender": str(group.get("sender") or "Remitente desconocido"),
            "action_count": int(group.get("action_count", 0) or 0),
            "status": _group_status_label(group),
            "last_activity_at": _format_datetime(group.get("last_activity_at")),
            "details": ":material/visibility: Ver",
        }
        for group in groups
    ]


def _group_status_label(group: dict[str, Any]) -> str:
    if int(group.get("failed_count", 0) or 0) > 0:
        return "Con errores"
    if int(group.get("pending_count", 0) or 0) > 0:
        return "En proceso"
    return "Completado"


@st.dialog(
    "Detalle del correo",
    width="large",
    icon=":material/chat_info:",
)
def _render_email_activity_detail(
    group: dict[str, Any],
    activities: list[dict[str, Any]],
) -> None:
    """Show one email's model response and every action performed for it."""
    st.subheader(str(group.get("subject") or "Correo sin asunto"))
    st.caption(
        f"{group.get('sender') or 'Remitente desconocido'} · "
        f"{_format_datetime(group.get('received_at'))}"
    )
    st.markdown(
        f"**{len(activities)} acciones** · "
        f"{int(group.get('completed_count', 0) or 0)} completadas · "
        f"{int(group.get('failed_count', 0) or 0)} fallidas · "
        f"{int(group.get('pending_count', 0) or 0)} pendientes"
    )

    response = ""
    for activity in reversed(activities):
        output = activity.get("output_data")
        if isinstance(output, dict) and str(output.get("respuesta") or "").strip():
            response = str(output["respuesta"]).strip()
            break

    st.subheader("Respuesta del asistente", icon=":material/smart_toy:")
    if response:
        st.markdown(response)
    else:
        st.info("Este correo no tiene una respuesta del modelo almacenada.")

    st.subheader(f"Acciones ejecutadas ({len(activities)})", icon=":material/checklist:")
    for activity in activities:
        output = activity.get("output_data")
        output = output if isinstance(output, dict) else {}
        tool_result = output.get("tool_result")
        usage = output.get("usage")
        error = str(activity.get("error_message") or "").strip()
        service = SERVICE_LABELS.get(
            str(activity.get("service")),
            str(activity.get("service") or "—").title(),
        )
        status = STATUS_LABELS.get(
            str(activity.get("status")),
            str(activity.get("status") or "—").title(),
        )

        with st.container(border=True):
            st.markdown(f"**{activity.get('title') or 'Actividad sin título'}**")
            st.caption(
                f"{service} · {status} · "
                f"{_format_datetime(activity.get('created_at'))}"
            )
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


def _select_email_for_dialog(groups: list[dict[str, Any]]) -> None:
    """Persist the row clicked by a transient dataframe button."""
    click = st.session_state.get("recent_email_activity_click")
    if not click:
        return
    row = int(click["row"])
    if 0 <= row < len(groups):
        st.session_state["email_activity_dialog"] = groups[row]


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

    email_activity_groups = database.list_recent_email_activity_groups(
        user_id=user["id"],
        limit=10,
    )
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

    st.subheader("Correos procesados", icon=":material/history:")
    st.caption(
        "Cada correo agrupa la respuesta del modelo y todas las acciones ejecutadas."
    )

    if email_activity_groups:
        st.caption("Pulsa Ver para revisar la respuesta y el detalle de sus acciones.")
        st.dataframe(
            _email_activity_rows(email_activity_groups),
            column_order=(
                "subject",
                "sender",
                "action_count",
                "status",
                "last_activity_at",
                "details",
            ),
            column_config={
                "subject": st.column_config.TextColumn("Correo", width="large"),
                "sender": st.column_config.TextColumn("Remitente", width="medium"),
                "action_count": st.column_config.NumberColumn(
                    "Acciones",
                    width="small",
                    format="%d",
                ),
                "status": st.column_config.TextColumn("Estado", width="small"),
                "last_activity_at": st.column_config.TextColumn(
                    "Última actividad",
                    width="medium",
                ),
                "details": st.column_config.ButtonColumn(
                    "Detalle",
                    width="small",
                    type="tertiary",
                    on_click=_select_email_for_dialog,
                    args=(email_activity_groups,),
                    key="recent_email_activity_click",
                ),
            },
            hide_index=True,
            height="content",
            key="recent-email-activity-table",
            lazy=False,
        )
        selected_group = st.session_state.pop("email_activity_dialog", None)
        if selected_group:
            selected_activities = database.list_actions_for_gmail_message(
                user_id=user["id"],
                gmail_message_db_id=int(selected_group["gmail_message_db_id"]),
            )
            _render_email_activity_detail(selected_group, selected_activities)
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
