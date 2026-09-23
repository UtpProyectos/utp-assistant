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
                "description": (
                    "Solo requisitos funcionales principales. Si existen códigos REQ-XX, "
                    "incluye únicamente esos elementos; no incluyas criterios de aceptación "
                    "ni actividades como requisitos separados."
                ),
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
    _tool(
        "buscar_cliente_crm",
        (
            "Busca en el CRM si el remitente del correo ya existe como cliente "
            "o cliente potencial usando su correo exacto. Úsala SIEMPRE antes de "
            "registrar_cliente_crm para evitar duplicados."
        ),
        {
            "correo": {
                "type": "string",
                "description": "Dirección de correo exacta del remitente.",
            },
        },
        ["correo"],
    ),
    _tool(
        "registrar_cliente_crm",
        (
            "Crea o actualiza un contacto en el CRM. "
            "Si ya existe (usa buscar_cliente_crm primero), envía solo los campos "
            "que hayan cambiado junto con 'cliente_id'. "
            "Si no existe, omite 'cliente_id' y se creará uno nuevo. "
            "Clasifica como 'Cliente potencial' salvo evidencia explícita de que ya es cliente."
        ),
        {
            "cliente_id": {
                "type": ["integer", "null"],
                "description": "ID del cliente existente. Null si es nuevo.",
            },
            "nombre": {"type": "string", "description": "Solo el nombre de pila."},
            "apellidos": {"type": ["string", "null"]},
            "tipo": {
                "type": "string",
                "enum": ["Cliente potencial", "Cliente"],
                "description": "Por defecto 'Cliente potencial'.",
            },
            "empresa": {"type": ["string", "null"]},
            "correo": {"type": ["string", "null"]},
            "telefono": {"type": ["string", "null"]},
            "rubro": {"type": ["string", "null"]},
            "notas": {"type": ["string", "null"]},
        },
        ["nombre", "tipo"],
    ),
]
