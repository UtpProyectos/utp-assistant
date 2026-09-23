"""CRM con asistente IA — Herramientas de Desarrollo Profesional TIC (UTP)."""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

load_dotenv()

import anthropic

import asistente
import database

app = Flask(__name__)
database.init_db()


@app.route("/")
def dashboard():
    resumen = database.resumen_pipeline()
    return render_template(
        "dashboard.html",
        activo="dashboard",
        clientes=len(database.listar_clientes()),
        resumen=resumen,
        pendientes=database.actividades_pendientes(),
    )


@app.route("/clientes", methods=["GET", "POST"])
def clientes():
    if request.method == "POST":
        if request.form.get("nombre", "").strip():
            database.crear_cliente(request.form)
        return redirect(url_for("clientes"))
    texto = request.args.get("q") or None
    return render_template(
        "clientes.html", activo="clientes",
        clientes=database.listar_clientes(texto), q=texto or "",
    )


@app.route("/clientes/<int:cliente_id>", methods=["GET", "POST"])
def cliente(cliente_id):
    if request.method == "POST":
        datos = dict(request.form)
        datos["cliente_id"] = cliente_id
        database.crear_actividad(datos)
        return redirect(url_for("cliente", cliente_id=cliente_id))
    ficha = database.detalle_cliente(cliente_id)
    if not ficha:
        return redirect(url_for("clientes"))
    return render_template("cliente.html", activo="clientes", **ficha)


@app.route("/actividades/<int:actividad_id>/completar", methods=["POST"])
def completar_actividad(actividad_id):
    database.completar_actividad(actividad_id)
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/oportunidades", methods=["GET", "POST"])
def oportunidades():
    if request.method == "POST":
        if request.form.get("descripcion", "").strip():
            database.crear_oportunidad(request.form)
        return redirect(url_for("oportunidades"))
    ops = database.listar_oportunidades()
    columnas = [(e, [o for o in ops if o["etapa"] == e]) for e in database.ETAPAS]
    return render_template(
        "oportunidades.html", activo="oportunidades",
        columnas=columnas, etapas=database.ETAPAS, clientes=database.listar_clientes(),
    )


@app.route("/oportunidades/<int:oportunidad_id>/etapa", methods=["POST"])
def mover_oportunidad(oportunidad_id):
    etapa = request.form.get("etapa")
    if etapa in database.ETAPAS:
        database.cambiar_etapa(oportunidad_id, etapa)
    return redirect(url_for("oportunidades"))


@app.route("/proyectos", methods=["GET", "POST"])
def proyectos():
    if request.method == "POST":
        if request.form.get("nombre", "").strip():
            database.crear_proyecto(request.form)
        return redirect(url_for("proyectos"))
    return render_template(
        "proyectos.html", activo="proyectos",
        proyectos=database.listar_proyectos(), estados=database.ESTADOS_PROYECTO,
        clientes=database.listar_clientes(),
    )


@app.route("/proyectos/<int:proyecto_id>/estado", methods=["POST"])
def cambiar_estado_proyecto(proyecto_id):
    estado = request.form.get("estado")
    if estado in database.ESTADOS_PROYECTO:
        database.actualizar_proyecto(proyecto_id, {"estado": estado})
    return redirect(url_for("proyectos"))


@app.route("/clientes/<int:cliente_id>/editar", methods=["POST"])
def editar_cliente(cliente_id):
    database.actualizar_cliente(cliente_id, dict(request.form))
    return redirect(url_for("cliente", cliente_id=cliente_id))


@app.route("/acciones")
def acciones():
    return render_template(
        "acciones.html", activo="acciones",
        acciones=database.listar_acciones_chatbot(),
    )


# ---------------- API REST (JSON) ----------------
# Consumida por el frontend o por el asistente central del grupo
# (registrar/actualizar clientes y proyectos, y dejar registro de acciones).

@app.route("/api/clientes", methods=["GET", "POST"])
def api_clientes():
    if request.method == "GET":
        # ?correo= identifica a un remitente por su dirección exacta; ?q= busca texto libre
        return jsonify(database.listar_clientes(request.args.get("q"), request.args.get("correo")))
    datos = request.get_json(silent=True) or {}
    if not datos.get("nombre", "").strip():
        return jsonify({"error": "El campo 'nombre' es obligatorio."}), 400
    nuevo = database.crear_cliente(datos)
    return jsonify({"ok": True, "cliente_id": nuevo}), 201


@app.route("/api/clientes/<int:cliente_id>", methods=["GET", "PUT"])
def api_cliente(cliente_id):
    if request.method == "GET":
        ficha = database.detalle_cliente(cliente_id)
        if not ficha:
            return jsonify({"error": "Cliente no encontrado."}), 404
        return jsonify(ficha)
    datos = request.get_json(silent=True) or {}
    if not database.actualizar_cliente(cliente_id, datos):
        return jsonify({"error": "Cliente no encontrado."}), 404
    return jsonify({"ok": True})


@app.route("/api/proyectos", methods=["GET", "POST"])
def api_proyectos():
    if request.method == "GET":
        return jsonify(database.listar_proyectos(request.args.get("estado")))
    datos = request.get_json(silent=True) or {}
    if not datos.get("nombre", "").strip() or not datos.get("cliente_id"):
        return jsonify({"error": "Los campos 'cliente_id' y 'nombre' son obligatorios."}), 400
    if not database.existe_cliente(datos["cliente_id"]):
        return jsonify({"error": "Cliente no encontrado."}), 404
    nuevo = database.crear_proyecto(datos)
    return jsonify({"ok": True, "proyecto_id": nuevo}), 201


@app.route("/api/proyectos/<int:proyecto_id>", methods=["PUT"])
def api_proyecto(proyecto_id):
    datos = request.get_json(silent=True) or {}
    if not database.actualizar_proyecto(proyecto_id, datos):
        return jsonify({"error": "Proyecto no encontrado."}), 404
    return jsonify({"ok": True})


@app.route("/api/oportunidades", methods=["GET"])
def api_oportunidades():
    return jsonify(database.listar_oportunidades(request.args.get("etapa")))


@app.route("/api/acciones-chatbot", methods=["GET", "POST"])
def api_acciones_chatbot():
    if request.method == "GET":
        return jsonify(database.listar_acciones_chatbot())
    datos = request.get_json(silent=True) or {}
    if not datos.get("accion"):
        return jsonify({"error": "El campo 'accion' es obligatorio."}), 400
    database.registrar_accion_chatbot(datos["accion"], datos.get("herramienta"), datos.get("detalle"))
    return jsonify({"ok": True}), 201


@app.route("/asistente")
def chat():
    return render_template(
        "chat.html", activo="asistente",
        con_key=bool(os.environ.get("ANTHROPIC_API_KEY")),
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    mensaje = (request.get_json(silent=True) or {}).get("mensaje", "").strip()
    if not mensaje:
        return jsonify({"error": "Escribe un mensaje."}), 400
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({"error": "Falta configurar ANTHROPIC_API_KEY (ver README / archivo .env)."}), 503
    try:
        return jsonify({"respuesta": asistente.responder(mensaje)})
    except anthropic.AuthenticationError:
        return jsonify({"error": "La API key configurada no es válida. Revisa el archivo .env."}), 503
    except anthropic.RateLimitError:
        return jsonify({"error": "Límite de uso de la API alcanzado. Espera un momento y reintenta."}), 503
    except anthropic.APIConnectionError:
        return jsonify({"error": "No hay conexión con la API de Claude. Verifica tu internet."}), 503
    except anthropic.APIStatusError as e:
        return jsonify({"error": f"Error de la API ({e.status_code}). Intenta de nuevo."}), 503


@app.route("/api/chat/reiniciar", methods=["POST"])
def api_chat_reiniciar():
    asistente.reiniciar()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
