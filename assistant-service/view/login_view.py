"""Google login view."""

import streamlit as st


def render_login() -> None:
    with st.container(horizontal_alignment="center"):
        st.title("UTP Assistant", icon=":material/smart_toy:")
        st.write("Tu asistente para organizar correos, reuniones y tareas.")

        with st.container(border=True, width="stretch"):
            st.subheader("Comenzar", icon=":material/login:")
            st.write("Inicia sesión con Google para conectar Gmail y Calendar.")
            if st.button(
                "Continuar con Google",
                icon=":material/account_circle:",
                type="primary",
                width="stretch",
            ):
                st.login()
