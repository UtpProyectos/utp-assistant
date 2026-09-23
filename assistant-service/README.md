# UTP Assistant — Gmail → IA → Calendar y Jira

Primera etapa funcional del caso UTPConsult. El usuario inicia sesión con Google,
el sistema revisa Gmail periódicamente, envía los correos nuevos al modelo y, si
el correo solicita una acción con información suficiente, opera reuniones en
Google Calendar y crea Historias o Tareas en Jira.

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
    └── Sí → operar Calendar y/o crear una incidencia en Jira
    ↓
PostgreSQL registra la acción
```

> En esta fase Streamlit realiza el login, la interfaz y dispara el polling
> mientras la sesión está activa. `UTPAssistant`, `GmailService`,
> `CalendarService`, `JiraService` y `EmailPollingService` están desacoplados
> para poder mover posteriormente la ejecución continua a FastAPI/worker sin
> reescribir la lógica.

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
│   ├── jira_rules.txt
│   ├── pdf_rules.txt
│   └── response_format.txt
├── services/
│   ├── gmail/
│   │   ├── gmail_service.py
│   │   └── email_poller.py
│   ├── calendar/
│   │   └── calendar_service.py
│   ├── jira/
│   │   └── jira_service.py
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
jira_rules.txt
pdf_rules.txt
response_format.txt
```

Solo se cargan las reglas que usa este MVP: Gmail, PDF, Calendar y Jira.

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
CALENDAR_BUSINESS_START=9
CALENDAR_BUSINESS_END=18
CALENDAR_ALTERNATIVE_DAYS=5
CALENDAR_SLOT_STEP_MINUTES=30

JIRA_BASE_URL=https://tu-espacio.atlassian.net
JIRA_EMAIL=correo-del-equipo
JIRA_API_TOKEN=token-de-atlassian
JIRA_PROJECT_KEY=UTP
# Opcionales si Jira usa nombres de tipos localizados:
JIRA_EPIC_ISSUE_TYPE=Epic
JIRA_STORY_ISSUE_TYPE=Story
JIRA_TASK_ISSUE_TYPE=Task
JIRA_START_DATE_FIELD_ID=customfield_10015
JIRA_TODO_STATUS_NAME=Por hacer
JIRA_EPIC_SIMILARITY_THRESHOLD=0.60
JIRA_TASK_SIMILARITY_THRESHOLD=0.78

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

Jira usa el mismo `.env` de `assistant-service`; no lee ni depende del `.env`
de la carpeta temporal `jira_integracion`. La cuenta configurada debe tener
permiso para crear incidencias en `JIRA_PROJECT_KEY`.

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

Cada acción conserva en `output_json` la respuesta final del modelo, el
resultado de la herramienta y el consumo de tokens, incluso cuando la acción
falla. El panel agrupa estas acciones por correo de origen: cada fila muestra
cuántas acciones produjo el mensaje y su estado conjunto. La opción `Ver` abre
un diálogo con la respuesta de la IA y el detalle de todas las acciones del
correo.

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
streamlit run main.py --server.port 8502
```

Abrir:

```text
http://localhost:8502
```

## Prueba recomendada de Calendar

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

## Prueba recomendada de Jira

1. Verifica las cuatro variables `JIRA_*` obligatorias en `.env`.
2. Envía un correo nuevo con un asunto como `UTPTEST - Solicitud TechCorp` y un
   cuerpo que identifique al cliente y describa explícitamente una funcionalidad
   o tarea a registrar.
3. El modelo decidirá si llama a `crear_ticket_en_jira` y enviará únicamente los
   datos presentes en el correo y sus PDF procesados.
4. Solo después de que Jira devuelva la clave y URL, el Assistant registrará la
   acción como completada en PostgreSQL y la mostrará como servicio `Jira`.

Una misma solicitud puede crear un ticket y agendar una reunión cuando ambas
acciones están justificadas. Si faltan datos obligatorios o Jira rechaza la
petición, la acción se guarda como fallida y el Assistant no afirma que se creó.

Para solicitudes de un proyecto o módulo con requisitos explícitos, el modelo
usa `crear_proyecto_en_jira`. El servicio compara el título con las Épicas
abiertas: reutiliza una similar o crea una Épica y después registra cada
requisito como una Tarea hija. Antes de crear cada Tarea también busca una
coincidencia para evitar duplicados al reintentar.

La deduplicación de Tareas prioriza el código `REQ-XX` y después compara el
contenido normalizado con `JIRA_TASK_SIMILARITY_THRESHOLD`. Cuando un documento
incluye requisitos codificados, los criterios de aceptación y actividades se
conservan como contexto, pero no se convierten en Tareas separadas.

La Épica y sus Tareas reciben `fecha_inicio` en el campo personalizado de Jira
configurado por `JIRA_START_DATE_FIELD_ID`, y `fecha_vencimiento` en el campo
nativo de vencimiento cuando el correo la indica explícitamente. Después de
crear cada incidencia, el servicio la mueve al estado `Por hacer` mediante la
transición configurada por `JIRA_TODO_STATUS_NAME`.

Si Calendar rechaza un horario por conflicto, el servicio busca el primer
espacio libre de los siguientes días hábiles dentro del horario configurado,
conserva la duración, agenda la alternativa y responde en el mismo hilo de
Gmail indicando el horario solicitado y el nuevo. El envío queda registrado
como una acción separada para poder detectar fallos de notificación.

Cada incidencia creada por Jira recibe además un comentario de actividad con
su origen, fechas y estado inicial. Al finalizar un proyecto, la Épica registra
cuántas Tareas se crearon, reutilizaron o fallaron.

## Ejecución del polling

El consentimiento offline guarda un `refresh_token` cifrado y permite renovar
el acceso sin volver a iniciar sesión. En esta etapa el fragmento de Streamlit
revisa Gmail cada 60 segundos mientras exista una sesión activa. Para operar
24/7 sin un navegador abierto, el mismo `EmailPollingService` debe ejecutarse
posteriormente desde un worker independiente.
