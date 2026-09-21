"""Google login view with clean Shadcn UI aesthetic."""

from __future__ import annotations

import streamlit as st
import streamlit_shadcn_ui as ui


SHADCN_CSS = """
<style>
/* Shadcn UI Dark Tokens */
:root {
    --card-bg: rgba(24, 24, 27, 0.75);
    --card-border: rgba(255, 255, 255, 0.1);
    --muted-fg: #a1a1aa;
    --accent-blue: #0057B8;
}

.shadcn-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 2rem;
    box-shadow: 0 4px 24px -2px rgba(0, 0, 0, 0.35);
    backdrop-filter: blur(12px);
    transition: border-color 0.2s ease;
}
.shadcn-card:hover {
    border-color: rgba(255, 255, 255, 0.18);
}

.brand-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(0, 87, 184, 0.15);
    color: #60a5fa;
    border: 1px solid rgba(0, 87, 184, 0.35);
    border-radius: 9999px;
    padding: 4px 14px;
    font-size: 0.8rem;
    font-weight: 500;
    margin-bottom: 1rem;
}

.feature-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 0.82rem;
    color: var(--muted-fg);
}
</style>
"""


def render_login() -> None:
    st.markdown(SHADCN_CSS, unsafe_allow_html=True)

    # Hero & Card Wrapper
    col_left, col_center, col_right = st.columns([1, 2.2, 1])
    with col_center:
        st.markdown(
            """
            <div style="text-align: center; margin-top: 2.5rem; margin-bottom: 2rem;">
                <div class="brand-badge">UTP Artificial Intelligence Assistant</div>
                <h1 style="font-size: 2.3rem; font-weight: 700; letter-spacing: -0.03em; margin: 0 0 0.5rem 0;">
                    UTP Assistant
                </h1>
                <p style="color: #a1a1aa; font-size: 1.05rem; margin: 0; line-height: 1.5;">
                    Asistente automatizado para la gestión inteligente de tus correos, calendarios y tareas universitarias.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container():
            st.markdown(
                """
                <div class="shadcn-card">
                    <h3 style="margin: 0 0 0.3rem 0; font-size: 1.25rem; font-weight: 600;">Iniciar sesión</h3>
                    <p style="color: #a1a1aa; font-size: 0.9rem; margin-bottom: 1.5rem;">
                        Accede de forma segura con tu cuenta de Google para habilitar el servicio.
                    </p>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 1.8rem;">
                        <span class="feature-pill">✉️ Gmail Monitor</span>
                        <span class="feature-pill">📅 Google Calendar</span>
                        <span class="feature-pill">🔒 OAuth 2.0</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Native OAuth Button (Styled to seamlessly fit Shadcn layout)
            if st.button(
                "Continuar con Google",
                icon=":material/account_circle:",
                type="primary",
                use_container_width=True,
            ):
                st.login()

            st.markdown(
                """
                <p style="text-align: center; color: #71717a; font-size: 0.78rem; margin-top: 1rem;">
                    Tus credenciales y datos están protegidos bajo cifrado Fernet AES-128.
                </p>
                """,
                unsafe_allow_html=True,
            )

