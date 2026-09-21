"""Calendar tools available to the model."""

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
        "Agenda una reunión si hay participante, fecha y hora confirmados.",
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
]
