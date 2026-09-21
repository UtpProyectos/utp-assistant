# UTP Assistant — MVP Gmail → IA → Google Calendar

Primera etapa funcional del caso UTPConsult. El usuario inicia sesión con Google,
el sistema revisa Gmail periódicamente, envía los correos nuevos al modelo y, si
el correo solicita una acción con información suficiente, consulta, crea,
reagenda o elimina el evento en Google Calendar.

## Flujo actual

```text
Google Login
    ↓
Streamlit
    ↓
Gmail (poll cada ~60 s)
    ↓
UTPAssistant
    ↓
OpenRouter / OpenAI
    ↓
¿requiere una acción?
    ├── No → registrar análisis
    └── Sí → leer / crear / reagendar / eliminar en Calendar
    ↓
PostgreSQL registra la acción
```

> En esta fase Streamlit realiza el login, la interfaz y dispara el polling
> mientras la sesión está activa. `UTPAssistant`, `GmailService`,
> `CalendarService` y `EmailPollingService` están desacoplados para poder mover
> posteriormente la ejecución continua a FastAPI/worker sin reescribir la lógica.

## Estructura

```text
assistant-service/
├── main.py
├── config.py
├── database.py
├── model/
│   ├── assistant.py
│   └── tools.py
├── prompts/
│   ├── system_prompt.txt        # Prompt padre compacto
│   ├── calendar_rules.txt
│   ├── pdf_rules.txt
│   └── response_format.txt
├── services/
│   ├── gmail/
│   │   ├── gmail_service.py
│   │   └── email_poller.py
│   ├── calendar/
│   │   └── calendar_service.py
│   └── pdf_reader.py
├── view/
│   ├── login_view.py
│   └── home_view.py
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── .env.example
├── requirements.txt
└── Dockerfile
```

## Prompt modular

Actualmente `model/assistant.py` carga solamente:

```text
system_prompt.txt
calendar_rules.txt
pdf_rules.txt
response_format.txt
```

Solo se cargan las reglas que usa este MVP: Gmail, PDF y Calendar.

## Seguridad durante las pruebas

El filtro por defecto es:

```text
is:unread in:inbox newer_than:2d
```

Así el primer inicio no procesa de golpe todo el historial pendiente. Para
procesar todos los no leídos, se puede cambiar a:

```text
is:unread in:inbox
```

## Variables de entorno

Copiar `.env.example` a `.env`.

Ejemplo con OpenRouter:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/utp_assistant

LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=tu_api_key
OPENROUTER_MODEL=openrouter/free

GOOGLE_CALENDAR_ID=primary
GMAIL_POLL_SECONDS=60
GMAIL_MAX_RESULTS=10
GMAIL_QUERY=is:unread in:inbox newer_than:2d
APP_TIMEZONE=America/Lima
```

Para OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=tu_api_key
OPENAI_MODEL=tu_modelo
```

No subir `.env` ni `.streamlit/secrets.toml` al repositorio.

## Google OAuth

Crear `.streamlit/secrets.toml` tomando como base
`.streamlit/secrets.toml.example`.

Local:

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
offline_redirect_uri = "http://localhost:8501/"
cookie_secret = "un-secreto-largo"
client_id = "...apps.googleusercontent.com"
client_secret = "..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[auth.client_kwargs]
scope = "openid profile email"
```

En Google Cloud deben existir exactamente ambos redirect URI. El primero es el
callback de login de Streamlit y el segundo recibe el consentimiento offline de
Gmail/Calendar para guardar el `refresh_token` cifrado.

Para Render cambia el redirect a:

```text
https://TU-SERVICIO.onrender.com/oauth2callback
```

Y agrega también:

```toml
offline_redirect_uri = "https://TU-SERVICIO.onrender.com/"
```

## PostgreSQL

El PostgreSQL actual es almacenamiento operativo del Assistant para:

- usuarios autenticados;
- token de acceso cifrado;
- correos ya procesados;
- acciones realizadas por la IA.

No es todavía el CRM simulado. El CRM será un servicio separado en la siguiente
etapa.

## Instalación

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Instalar:

```bash
pip install -r requirements.txt
```

Ejecutar:

```bash
streamlit run main.py
```

Abrir:

```text
http://localhost:8501
```

## Prueba recomendada

1. Inicia sesión con Google.
2. Mándate un correo con asunto:

```text
UTPTEST - Reunión TechCorp
```

3. Contenido de ejemplo:

```text
Hola,
¿Podemos reunirnos el 23 de septiembre de 2026 a las 4:00 p. m. para revisar
el módulo de pagos?

Saludos,
Ana
```

4. El Assistant revisará Gmail en el siguiente ciclo.
5. El modelo decidirá si llama a `crear_reunion`.
6. Calendar validará que el horario esté disponible.
7. Si Calendar confirma, el evento aparecerá en el calendario y la acción se
   mostrará en el dashboard.

## Ejecución del polling

El consentimiento offline guarda un `refresh_token` cifrado y permite renovar
el acceso sin volver a iniciar sesión. En esta etapa el fragmento de Streamlit
revisa Gmail cada 60 segundos mientras exista una sesión activa. Para operar
24/7 sin un navegador abierto, el mismo `EmailPollingService` debe ejecutarse
posteriormente desde un worker independiente.
