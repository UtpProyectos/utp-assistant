"""Welcome view shown after Google login."""

from typing import Any

import streamlit as st

from database import Database


def render_home(user: dict[str, Any], database: Database) -> None:
    with st.sidebar:
        st.write(f"**{user['name']}**")
        st.caption(user["email"])
        if st.button("Cerrar sesión", icon=":material/logout:"):
            st.logout()

    st.title("Bienvenido a UTP Assistant", icon=":material/waving_hand:")
    st.write(
        "UTP Assistant te ayudará en lo que necesites: organizar correos, "
        "coordinar reuniones y dar seguimiento a tus tareas."
    )

    st.subheader("Últimas actividades", icon=":material/history:")
    activities = database.list_recent_actions(user_id=user["id"], limit=10)

    if activities:
        st.dataframe(
            activities,
            width="stretch",
            hide_index=True,
            column_config={
                "id": None,
                "title": "Actividad",
                "service": "Servicio",
                "status": "Estado",
                "created_at": "Creada",
                "completed_at": "Completada",
            },
        )
    else:
        with st.container(border=True):
            st.write("El Assistant todavía no ha realizado actividades.")
            st.caption(
                "Aquí aparecerán las acciones de Gmail, Calendar y el modelo."
            )
