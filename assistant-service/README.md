# UTP Assistant

Asistente universitario que conecta Gmail y Google Calendar para automatizar
la organización de correos, reuniones y tareas mediante IA.

## Arquitectura

```
assistant-service/
├── main.py                 # Entry point – arranca Streamlit
├── config.py               # Settings y scopes de Google
├── database.py             # SQLite: users, oauth, gmail_sync, actions
├── requirements.txt
├── Dockerfile
├── .streamlit/
│   ├── config.toml         # Tema y configuración de Streamlit
│   └── secrets.toml        # Credenciales OAuth (no en Git)
├── view/
│   ├── login_view.py       # Pantalla de login con Google
│   └── home_view.py        # Bienvenida + últimas actividades
├── services/
│   ├── gmail/
│   │   └── gmail_service.py    # Gmail API wrapper (list, get, watch, history)
│   ├── calendar/
│   │   └── calendar_service.py # Calendar API wrapper (CRUD + availability)
│   ├── crm/                # (reservado – otro equipo)
│   ├── jira/               # (reservado – otro equipo)
│   └── promts/             # (reservado – otro equipo)
└── model/                  # (futuro – modelo IA)
```

## Tablas de la Base de Datos

| Tabla               | Propósito                                              |
|---------------------|--------------------------------------------------------|
| `users`             | Usuarios logueados con Google (sub, email, nombre)     |
| `oauth_credentials` | Access token encriptado + scopes por usuario           |
| `gmail_sync_state`  | Estado de sincronización: historyId, watch expiration  |
| `gmail_messages`    | Correos vistos – para saber qué ya se procesó         |
| `actions`           | Acciones de la IA (pending/running/completed/failed)   |

## Flujo

1. El usuario abre la app → ve la pantalla de login
2. Hace clic en "Continuar con Google" → OAuth con Gmail + Calendar scopes
3. Se guarda/actualiza el usuario en la DB
4. Se guarda el access token encriptado
5. Se muestra la página de bienvenida con últimas actividades
6. (Futuro) El modelo escucha Gmail vía `watch()` + `get_history_changes()`

## Configuración

### 1. Crear `.streamlit/secrets.toml`

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "genera-un-valor-largo-aleatorio"
client_id = "tu-google-client-id"
client_secret = "tu-google-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
expose_tokens = ["id", "access"]

[auth.client_kwargs]
scope = "openid profile email https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar"
prompt = "consent"
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Ejecutar

```bash
streamlit run main.py
```

## Servicios disponibles para el modelo

### GmailService
- `list_messages()` – listar correos
- `get_message(id)` – detalle de un correo
- `get_attachments(id)` – adjuntos
- `mark_as_read(id)` – marcar como leído
- `watch(topic)` – activar push notifications (Pub/Sub)
- `stop_watch()` – desactivar push notifications
- `get_history_changes(history_id)` – cambios incrementales
- `list_unread_messages()` – no leídos en INBOX
- `get_profile()` – perfil del usuario (email, historyId)

### CalendarService
- `list_events()` – próximos eventos
- `check_availability(start, end)` – verificar disponibilidad
- `create_event(...)` – crear evento
- `get_event(id)` – detalle de un evento
- `update_event(id, ...)` – actualizar evento
- `delete_event(id)` – eliminar evento
