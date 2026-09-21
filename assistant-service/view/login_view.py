"""Google authentication views built with streamlit-shadcn-ui."""

from __future__ import annotations

import streamlit as st
import streamlit_shadcn_ui as ui


def render_login() -> None:
    """Render the initial Google identity login."""
    _, center, _ = st.columns([1, 1.7, 1])
    with center:
        st.title(
            "UTP Assistant",
            icon=":material/smart_toy:",
            text_alignment="center",
        )
        st.caption(
            "Gestiona correos y coordina reuniones de UTPConsult con un asistente "
            "conectado a Gmail y Google Calendar.",
            text_alignment="center",
        )
        ui.badges(
            [
                ("Gmail", "secondary"),
                ("Google Calendar", "secondary"),
                ("OAuth 2.0", "outline"),
            ],
            key="login-features",
            width="stretch",
        )
        ui.card(
            title="Acceso seguro",
            description="Usa tu cuenta de Google para identificarte.",
            content=(
                "Después del login autorizaremos el acceso offline necesario para "
                "renovar Gmail y Calendar sin pedir credenciales nuevamente."
            ),
            footer="Los tokens se almacenan cifrados.",
            key="login-card",
        )
        if ui.button(
            "Continuar con Google",
            key="google-login-button",
            size="lg",
            width="stretch",
        ):
            st.login()
        st.caption(
            "El asistente solo solicita identidad, Gmail y Calendar.",
            text_alignment="center",
        )


def render_google_authorization(
    authorization_url: str,
    error_message: str | None = None,
) -> None:
    """Ask a logged-in user for durable Gmail and Calendar authorization."""
    _, center, _ = st.columns([1, 1.7, 1])
    with center:
        st.title(
            "Conecta tus servicios",
            icon=":material/add_link:",
            text_alignment="center",
        )
        st.caption(
            "El login está completo. Autoriza Gmail y Calendar para activar el monitor.",
            text_alignment="center",
        )
        ui.badges(
            [
                ("Gmail modify", "secondary"),
                ("Calendar", "secondary"),
                ("Acceso offline", "outline"),
            ],
            key="authorization-scopes",
            width="stretch",
        )
        if error_message:
            ui.alert(
                "No se completó la autorización",
                error_message,
                variant="destructive",
                key="authorization-error",
            )
        ui.card(
            title="Autorización de Google",
            description="Este paso habilita la renovación automática del token.",
            content=(
                "Google mostrará los permisos de Gmail y Calendar. El refresh token "
                "se guardará cifrado y nunca se mostrará en la interfaz."
            ),
            footer="Puedes revocar el acceso desde tu cuenta de Google.",
            key="authorization-card",
        )
        ui.link_button(
            "Autorizar Gmail y Calendar",
            authorization_url,
            key="authorize-google-link",
            size="lg",
            target="_self",
            width="stretch",
        )
        if ui.button(
            "Cerrar sesión",
            key="authorization-logout",
            variant="ghost",
            width="stretch",
        ):
            st.logout()
