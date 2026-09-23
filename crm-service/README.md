# CRM Seguro — CRM con asistente IA

CRM local con **API REST** para gestionar **clientes**, **proyectos**, **ventas potenciales
(pipeline de oportunidades)** y **actividades de seguimiento**, con un **asistente IA
integrado** (API de Claude) que consulta la base de datos real y puede **registrar o
actualizar clientes y proyectos** por chat. Todas las acciones del asistente quedan
registradas en la tabla `acciones_chatbot`, visible en el frontend ("Acciones IA").

Módulo CRM del proyecto grupal del curso **Herramientas de Desarrollo Profesional TIC** (UTP).
El asistente central del grupo (correos / Jira / Calendar) se integra con este CRM a través
de la API REST.

## Tecnologías

- **Python 3 + Flask** — aplicación web
- **SQLite** — base de datos en un solo archivo (`crm.db`)
- **API de Claude (SDK `anthropic`)** — chatbot con *tool use*: el modelo llama herramientas
  de solo lectura (`buscar_clientes`, `listar_oportunidades`, `resumen_pipeline`, etc.),
  la app ejecuta las consultas SQL y el modelo redacta la respuesta con datos reales
- **Docker / Docker Compose** — contenedorización

## Configurar la API key (requerido para el asistente IA)

1. Crear una key en <https://platform.claude.com> (sección **API keys**).
2. Copiar `.env.example` como `.env`:
   ```bash
   cp .env.example .env
   ```
3. Pegar la key en la variable `ANTHROPIC_API_KEY` del archivo `.env`.

> El CRM funciona sin la key (clientes, ventas, dashboard); solo el chat del
> asistente la necesita. La key **nunca** se escribe en el código ni se sube al
> repositorio (`.env` está en `.gitignore`).

## Ejecutar con Docker (recomendado)

```bash
docker compose up --build
```

Abrir <http://localhost:5000>. Los datos se guardan en el volumen `datos_crm`.

## Ejecutar sin Docker

```bash
pip install -r requirements.txt
python app.py
```

Abrir <http://localhost:5000>.

## Estructura

```
crm/
├── app.py              # Rutas Flask (dashboard, clientes, oportunidades, chat)
├── database.py         # Esquema SQLite, datos de ejemplo y consultas
├── asistente.py        # Integración con la API de Claude (tool use)
├── templates/          # Vistas HTML (Jinja2)
├── static/style.css    # Estilos
├── Dockerfile
├── docker-compose.yml
└── .env.example        # Plantilla de configuración (copiar a .env)
```

## API REST

Base: `http://localhost:5000`. Cuerpos en JSON.

| Método | Endpoint | Descripción |
|---|---|---|
| GET | `/api/clientes?q=texto` | Listar / buscar clientes (nombre, empresa, rubro, correo, teléfono, notas) |
| GET | `/api/clientes?correo=x@y.com` | Identificar a un remitente por correo exacto (evita duplicados) |
| POST | `/api/clientes` | Registrar cliente (`nombre` obligatorio; `apellidos` opcional; `tipo`: "Cliente potencial" por defecto o "Cliente") |
| GET | `/api/clientes/<id>` | Ficha completa (cliente + oportunidades + actividades) |
| PUT | `/api/clientes/<id>` | Actualizar campos del cliente |
| GET | `/api/proyectos?estado=En curso` | Listar proyectos |
| POST | `/api/proyectos` | Registrar proyecto (`cliente_id`, `nombre`) |
| PUT | `/api/proyectos/<id>` | Actualizar proyecto (estado, fechas, etc.) |
| GET | `/api/oportunidades?etapa=Negociación` | Listar ventas potenciales |
| GET | `/api/acciones-chatbot` | Log de acciones del asistente |
| POST | `/api/acciones-chatbot` | Registrar una acción (para el asistente central del grupo) |
| POST | `/api/chat` | Conversar con el asistente IA (`{"mensaje": "..."}`) |

Ejemplo (registrar un cliente desde otro sistema del grupo):

```bash
curl -X POST http://localhost:5000/api/clientes \
  -H "Content-Type: application/json" \
  -d '{"nombre": "Ana Ruiz", "empresa": "Minera Sur", "correo": "ana@minerasur.pe"}'
```

## Ejemplos de preguntas para el asistente

- «¿Cuánto suma el pipeline abierto?»
- «¿Qué acciones de seguimiento tengo pendientes esta semana?»
- «Muéstrame las oportunidades en negociación»
- «Redacta un correo de seguimiento para la Clínica San Rafael»
- «¿Qué cliente tiene la oportunidad más grande y en qué etapa está?»
- «Registra al cliente Pedro Gómez de la empresa AgroExport, rubro agroindustria»
- «Cambia el estado del proyecto de diagnóstico ISO a En curso»

## Notas para el informe del curso

- El *system prompt* del asistente (en `asistente.py`) aplica técnicas de **prompt
  engineering**: definición de rol, contexto del dominio, reglas de formato y
  restricción a datos reales (las herramientas evitan alucinaciones).
- La app está **contenedorizada** (Dockerfile + Compose) y lista para integrarse a un
  pipeline CI/CD (build → pruebas → imagen Docker → despliegue).
- Modelo utilizado: `claude-opus-4-8` con *adaptive thinking*.
