"""Calendar and Jira tools available to the model."""

DATETIME = {
    "type": "string",
    "description": "Fecha ISO 8601, por ejemplo 2026-09-23T16:00:00-05:00.",
}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOLS = [
    _tool(
        "leer_agenda",
        "Lee eventos de Calendar en un rango. Úsala para localizar el ID de una reunión.",
        {
            "fecha_inicio": DATETIME,
            "fecha_fin": DATETIME,
            "limite": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        ["fecha_inicio", "fecha_fin"],
    ),
    _tool(
        "crear_reunion",
        (
            "Agenda una reunión con datos confirmados. Si el horario está ocupado, "
            "reserva automáticamente el siguiente espacio laboral y notifica por Gmail."
        ),
        {
            "titulo": {"type": "string"},
            "descripcion": {"type": "string"},
            "fecha_inicio": DATETIME,
            "fecha_fin": DATETIME,
            "participantes": {"type": "array", "items": {"type": "string"}},
        },
        ["titulo", "descripcion", "fecha_inicio", "fecha_fin", "participantes"],
    ),
    _tool(
        "reagendar_reunion",
        "Cambia el horario de una reunión existente usando su ID real de Calendar.",
        {"evento_id": {"type": "string"}, "fecha_inicio": DATETIME, "fecha_fin": DATETIME},
        ["evento_id", "fecha_inicio", "fecha_fin"],
    ),
    _tool(
        "eliminar_reunion",
        "Elimina una reunión existente usando su ID real de Calendar.",
        {"evento_id": {"type": "string"}},
        ["evento_id"],
    ),
    _tool(
        "crear_ticket_en_jira",
        (
            "Crea una Historia o Tarea en Jira a partir de datos explícitos de un "
            "correo y sus adjuntos."
        ),
        {
            "tipo": {"type": "string", "enum": ["Historia", "Tarea"]},
            "titulo": {"type": "string"},
            "cliente": {"type": "string"},
            "empresa": {"type": ["string", "null"]},
            "descripcion": {"type": "string"},
            "requisitos": {"type": "array", "items": {"type": "string"}},
            "fecha_inicio": {
                "type": "string",
                "description": "Fecha de envío del correo en formato AAAA-MM-DD.",
            },
            "fecha_vencimiento": {
                "type": ["string", "null"],
                "description": "Fecha AAAA-MM-DD solo si fue indicada explícitamente.",
            },
            "adjuntos": {"type": "array", "items": {"type": "string"}},
            "subtareas": {"type": "array", "items": {"type": "string"}},
        },
        [
            "tipo",
            "titulo",
            "cliente",
            "empresa",
            "descripcion",
            "requisitos",
            "fecha_inicio",
            "fecha_vencimiento",
            "adjuntos",
            "subtareas",
        ],
    ),
    _tool(
        "crear_proyecto_en_jira",
        (
            "Busca una Épica abierta similar; la reutiliza o crea una nueva y "
            "registra cada requisito explícito como una Tarea hija."
        ),
        {
            "titulo": {
                "type": "string",
                "description": "Nombre estable del proyecto o módulo, incluyendo la empresa.",
            },
            "cliente": {"type": "string"},
            "empresa": {"type": ["string", "null"]},
            "descripcion": {"type": "string"},
            "requisitos": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "fecha_inicio": {
                "type": "string",
                "description": "Fecha de envío del correo en formato AAAA-MM-DD.",
            },
            "fecha_vencimiento": {"type": ["string", "null"]},
            "adjuntos": {"type": "array", "items": {"type": "string"}},
        },
        [
            "titulo",
            "cliente",
            "empresa",
            "descripcion",
            "requisitos",
            "fecha_inicio",
            "fecha_vencimiento",
            "adjuntos",
        ],
    ),
]
