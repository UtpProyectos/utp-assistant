"""Asistente IA del CRM: chat conectado a la API de OpenAI con tool use."""
import json
import os
from datetime import date
from openai import OpenAI

import database

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
MAX_TURNOS_HISTORIAL = 20  # pares usuario/asistente que se conservan en memoria

SYSTEM = """Eres el asistente inteligente de un CRM de una consultora peruana de ciberseguridad.
Tu trabajo es ayudar al usuario a consultar y analizar sus clientes, ventas potenciales
(oportunidades) y actividades de seguimiento.

Ademas de consultar, puedes REGISTRAR y ACTUALIZAR clientes y proyectos cuando el
usuario te lo pida (por ejemplo: "registra al cliente Ana Ruiz de Minera Sur" o
"cambia el estado del proyecto 2 a Finalizado").

Reglas:
- Responde siempre en espanol, de forma clara y breve.
- Usa las herramientas para obtener datos reales de la base de datos; nunca inventes
  clientes, montos ni fechas. Si no hay datos, dilo.
- Antes de registrar un contacto, verifica que no exista (busca por correo) para evitar duplicados.
"""

def _tool(name, desc, props, req=None):
    t = {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": props
            }
        }
    }
    if req:
        t["function"]["parameters"]["required"] = req
    return t

TOOLS = [
    _tool("buscar_clientes", "Busca contactos. Usa 'correo' (busqueda exacta) o 'texto'. Sin parametros, lista todos.",
          {"texto": {"type": "string"}, "correo": {"type": "string"}}),
    _tool("detalle_cliente", "Devuelve la ficha completa de un cliente.",
          {"cliente_id": {"type": "integer"}}, ["cliente_id"]),
    _tool("listar_oportunidades", "Lista las oportunidades de venta.",
          {"etapa": {"type": "string", "enum": database.ETAPAS}}),
    _tool("resumen_pipeline", "Devuelve el resumen del pipeline de ventas.", {}),
    _tool("actividades_pendientes", "Lista las proximas acciones pendientes.", {}),
    _tool("listar_proyectos", "Lista los proyectos en ejecucion.",
          {"estado": {"type": "string", "enum": database.ESTADOS_PROYECTO}}),
    _tool("registrar_cliente", "Registra un contacto nuevo en el CRM.",
          {
              "nombre": {"type": "string"},
              "apellidos": {"type": "string"},
              "tipo": {"type": "string", "enum": database.TIPOS_CLIENTE},
              "empresa": {"type": "string"},
              "correo": {"type": "string"},
              "telefono": {"type": "string"},
              "rubro": {"type": "string"},
              "origen": {"type": "string"},
              "notas": {"type": "string"}
          }, ["nombre"]),
    _tool("actualizar_cliente", "Actualiza los datos de un contacto existente.",
          {
              "cliente_id": {"type": "integer"},
              "nombre": {"type": "string"},
              "apellidos": {"type": "string"},
              "tipo": {"type": "string", "enum": database.TIPOS_CLIENTE},
              "empresa": {"type": "string"},
              "correo": {"type": "string"},
              "telefono": {"type": "string"},
              "rubro": {"type": "string"},
              "origen": {"type": "string"},
              "notas": {"type": "string"}
          }, ["cliente_id"]),
    _tool("registrar_proyecto", "Registra un proyecto para un cliente existente.",
          {
              "cliente_id": {"type": "integer"},
              "nombre": {"type": "string"},
              "descripcion": {"type": "string"},
              "estado": {"type": "string", "enum": database.ESTADOS_PROYECTO},
              "fecha_inicio": {"type": "string"},
              "fecha_fin": {"type": "string"}
          }, ["cliente_id", "nombre"]),
    _tool("actualizar_proyecto", "Actualiza un proyecto existente.",
          {
              "proyecto_id": {"type": "integer"},
              "nombre": {"type": "string"},
              "descripcion": {"type": "string"},
              "estado": {"type": "string", "enum": database.ESTADOS_PROYECTO},
              "fecha_inicio": {"type": "string"},
              "fecha_fin": {"type": "string"}
          }, ["proyecto_id"])
]

def _registrar_cliente(inp):
    nuevo = database.crear_cliente(inp)
    return {"ok": True, "cliente_id": nuevo, "mensaje": "Cliente registrado."}

def _actualizar_cliente(inp):
    datos = {k: v for k, v in inp.items() if k != "cliente_id"}
    ok = database.actualizar_cliente(inp["cliente_id"], datos)
    return {"ok": ok, "mensaje": "Cliente actualizado." if ok else "No existe un cliente con ese ID."}

def _registrar_proyecto(inp):
    if not database.existe_cliente(inp["cliente_id"]):
        return {"ok": False, "mensaje": "No existe un cliente con ese ID."}
    nuevo = database.crear_proyecto(inp)
    return {"ok": True, "proyecto_id": nuevo, "mensaje": "Proyecto registrado."}

def _actualizar_proyecto(inp):
    datos = {k: v for k, v in inp.items() if k != "proyecto_id"}
    ok = database.actualizar_proyecto(inp["proyecto_id"], datos)
    return {"ok": ok, "mensaje": "Proyecto actualizado." if ok else "No existe un proyecto con ese ID."}

_FUNCIONES = {
    "buscar_clientes": lambda inp: database.listar_clientes(inp.get("texto"), inp.get("correo")),
    "detalle_cliente": lambda inp: database.detalle_cliente(inp["cliente_id"]),
    "listar_oportunidades": lambda inp: database.listar_oportunidades(inp.get("etapa")),
    "resumen_pipeline": lambda inp: database.resumen_pipeline(),
    "actividades_pendientes": lambda inp: database.actividades_pendientes(),
    "listar_proyectos": lambda inp: database.listar_proyectos(inp.get("estado")),
    "registrar_cliente": _registrar_cliente,
    "actualizar_cliente": _actualizar_cliente,
    "registrar_proyecto": _registrar_proyecto,
    "actualizar_proyecto": _actualizar_proyecto,
}

_historial = []

def reiniciar():
    _historial.clear()

def responder(mensaje_usuario):
    """Envia el mensaje al modelo y devuelve el texto de respuesta."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    _historial.append({"role": "user", "content": mensaje_usuario})
    mensajes = [{"role": "system", "content": SYSTEM.format(hoy=date.today().isoformat())}] + _historial
    
    database.registrar_accion_chatbot("consulta", detalle=mensaje_usuario)

    while True:
        respuesta = client.chat.completions.create(
            model=MODEL,
            messages=mensajes,
            tools=TOOLS,
            tool_choice="auto",
            reasoning_effort="none"
        )
        msg = respuesta.choices[0].message
        
        if msg.tool_calls:
            mensajes.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                fn_name = call.function.name
                try:
                    inp = json.loads(call.function.arguments)
                    datos = _FUNCIONES[fn_name](inp)
                    database.registrar_accion_chatbot("herramienta", herramienta=fn_name, detalle=json.dumps(inp, ensure_ascii=False))
                    res_content = json.dumps(datos, ensure_ascii=False, default=str)
                except Exception as e:
                    database.registrar_accion_chatbot("error", herramienta=fn_name, detalle=str(e))
                    res_content = f"Error: {e}"
                
                mensajes.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": res_content
                })
        else:
            texto = msg.content or "No pude generar una respuesta."
            break

    database.registrar_accion_chatbot("respuesta", detalle=texto[:500])
    _historial.append({"role": "assistant", "content": texto})
    del _historial[:-MAX_TURNOS_HISTORIAL * 2]
    return texto
