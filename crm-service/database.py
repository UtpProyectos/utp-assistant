"""Capa de datos CRM v2 — PostgreSQL en Neon (BD compartida del grupo)."""
import os
from datetime import date, timedelta
import psycopg2, psycopg2.extras

DATABASE_URL = os.environ.get("UTP_DATABASE_PATH")
ETAPAS = ["Prospecto","Contactado","Propuesta enviada","Negociacion","Ganada","Perdida"]
ETAPAS_ABIERTAS = ETAPAS[:4]
ESTADOS_PROYECTO = ["Planificado","En curso","En pausa","Finalizado","Cancelado"]
TIPOS_CLIENTE = ["Cliente potencial","Cliente"]

def get_db():
    return psycopg2.connect(DATABASE_URL)

def _cur(con):
    return con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    con = get_db(); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS clientes(id SERIAL PRIMARY KEY,nombre TEXT NOT NULL,apellidos TEXT DEFAULT '',empresa TEXT,correo TEXT,telefono TEXT,rubro TEXT,origen TEXT,notas TEXT,tipo TEXT NOT NULL DEFAULT 'Cliente potencial',creado_en TEXT DEFAULT CURRENT_DATE::TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS oportunidades(id SERIAL PRIMARY KEY,cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,descripcion TEXT NOT NULL,monto REAL DEFAULT 0,etapa TEXT NOT NULL DEFAULT 'Prospecto',probabilidad INTEGER DEFAULT 50,cierre_estimado TEXT,creado_en TEXT DEFAULT CURRENT_DATE::TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS proyectos(id SERIAL PRIMARY KEY,cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,nombre TEXT NOT NULL,descripcion TEXT,estado TEXT NOT NULL DEFAULT 'Planificado',fecha_inicio TEXT,fecha_fin TEXT,creado_en TEXT DEFAULT CURRENT_DATE::TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS acciones_chatbot(id SERIAL PRIMARY KEY,creado_en TEXT DEFAULT TO_CHAR(NOW(),'YYYY-MM-DD HH24:MI:SS'),accion TEXT NOT NULL,herramienta TEXT,detalle TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS actividades(id SERIAL PRIMARY KEY,cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,tipo TEXT NOT NULL,detalle TEXT,fecha TEXT DEFAULT CURRENT_DATE::TEXT,proxima_accion TEXT,proxima_fecha TEXT,completada INTEGER DEFAULT 0)""")
    con.commit()
    c2 = _cur(con); c2.execute("SELECT COUNT(*) AS n FROM clientes")
    if c2.fetchone()["n"] == 0: _seed(con)
    c.close(); c2.close(); con.close()

def _seed(con):
    hoy = date.today(); c = con.cursor()
    datos = [("Maria","Torres Vega","Clinica San Rafael","mtorres@sanrafael.pe","999-111-222","Salud","Referido","Interesada en auditoria de seguridad anual.","Cliente"),
             ("Jorge","Salas Rojas","Ferreteria El Tornillo","jsalas@eltornillo.pe","998-333-444","Retail","LinkedIn","Pyme, presupuesto limitado.","Cliente potencial"),
             ("Lucia","Fernandez Bravo","Banco Andino","lfernandez@bandino.pe","997-555-666","Financiero","Evento","Contacto del evento de ciberseguridad.","Cliente"),
             ("Ricardo","Palma Quispe","Transportes RPQ","rpalma@rpq.pe","996-777-888","Logistica","Web","Sufrio incidente de ransomware en 2025.","Cliente potencial")]
    ids=[]
    for d in datos:
        c.execute("INSERT INTO clientes(nombre,apellidos,empresa,correo,telefono,rubro,origen,notas,tipo) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",d)
        ids.append(c.fetchone()[0])
    c.executemany("INSERT INTO oportunidades(cliente_id,descripcion,monto,etapa,probabilidad,cierre_estimado) VALUES(%s,%s,%s,%s,%s,%s)",
        [(ids[0],"Auditoria anual de seguridad",18000,"Propuesta enviada",60,str(hoy+timedelta(days=20))),
         (ids[1],"Implementacion de firewall",4500,"Contactado",40,str(hoy+timedelta(days=35))),
         (ids[2],"Consultoria ISO 27001",32000,"Negociacion",75,str(hoy+timedelta(days=12))),
         (ids[3],"Plan de respuesta a incidentes",12000,"Prospecto",25,str(hoy+timedelta(days=60))),
         (ids[0],"Capacitacion de concientizacion",3500,"Ganada",100,str(hoy-timedelta(days=10)))])
    c.executemany("INSERT INTO actividades(cliente_id,tipo,detalle,fecha,proxima_accion,proxima_fecha,completada) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        [(ids[0],"Reunion","Presentacion de propuesta",str(hoy-timedelta(days=5)),"Llamar para consultar",str(hoy+timedelta(days=2)),0),
         (ids[2],"Llamada","Negociacion de alcance",str(hoy-timedelta(days=2)),"Enviar propuesta ajustada",str(hoy+timedelta(days=1)),0),
         (ids[1],"Correo","Se envio cotizacion de firewall",str(hoy-timedelta(days=15)),"Hacer seguimiento",str(hoy-timedelta(days=3)),0),
         (ids[3],"Reunion","Primer contacto ransomware",str(hoy-timedelta(days=8)),"Enviar diagnostico",str(hoy+timedelta(days=5)),0)])
    c.executemany("INSERT INTO proyectos(cliente_id,nombre,descripcion,estado,fecha_inicio,fecha_fin) VALUES(%s,%s,%s,%s,%s,%s)",
        [(ids[0],"Capacitacion 2026","Talleres de phishing","En curso",str(hoy-timedelta(days=7)),str(hoy+timedelta(days=30))),
         (ids[2],"Diagnostico ISO 27001","Levantamiento de brechas","Planificado",str(hoy+timedelta(days=15)),None)])
    con.commit(); c.close()

def listar_clientes(texto=None,correo=None):
    con=get_db();c=_cur(con)
    if correo: c.execute("SELECT * FROM clientes WHERE LOWER(correo)=LOWER(%s)",(correo.strip(),))
    elif texto:
        q=f"%{texto}%"
        c.execute("SELECT * FROM clientes WHERE nombre ILIKE %s OR apellidos ILIKE %s OR (nombre||' '||apellidos) ILIKE %s OR empresa ILIKE %s OR rubro ILIKE %s OR notas ILIKE %s OR correo ILIKE %s OR telefono ILIKE %s ORDER BY nombre",(q,q,q,q,q,q,q,q))
    else: c.execute("SELECT * FROM clientes ORDER BY nombre")
    r=[dict(x) for x in c.fetchall()];c.close();con.close();return r

def detalle_cliente(cliente_id):
    con=get_db();c=_cur(con)
    c.execute("SELECT * FROM clientes WHERE id=%s",(cliente_id,));cl=c.fetchone()
    if not cl:c.close();con.close();return None
    c.execute("SELECT * FROM oportunidades WHERE cliente_id=%s ORDER BY creado_en DESC",(cliente_id,));ops=[dict(x) for x in c.fetchall()]
    c.execute("SELECT * FROM actividades WHERE cliente_id=%s ORDER BY fecha DESC",(cliente_id,));acts=[dict(x) for x in c.fetchall()]
    c.close();con.close();return{"cliente":dict(cl),"oportunidades":ops,"actividades":acts}

def listar_oportunidades(etapa=None):
    con=get_db();c=_cur(con);sql="SELECT o.*,TRIM(cl.nombre||' '||COALESCE(cl.apellidos,'')) AS cliente,cl.empresa FROM oportunidades o JOIN clientes cl ON cl.id=o.cliente_id"
    if etapa:c.execute(sql+" WHERE o.etapa=%s ORDER BY o.cierre_estimado",(etapa,))
    else:c.execute(sql+" ORDER BY o.cierre_estimado")
    r=[dict(x) for x in c.fetchall()];c.close();con.close();return r

def resumen_pipeline():
    con=get_db();c=_cur(con)
    c.execute("SELECT etapa,COUNT(*) AS cantidad,SUM(monto) AS monto_total,SUM(monto*probabilidad/100.0) AS monto_ponderado FROM oportunidades GROUP BY etapa")
    filas={x["etapa"]:dict(x) for x in c.fetchall()}
    c.execute("SELECT COUNT(*) AS c,COALESCE(SUM(monto),0) AS m FROM oportunidades WHERE etapa NOT IN ('Ganada','Perdida')")
    t=c.fetchone();c.close();con.close()
    return{"por_etapa":[filas.get(e,{"etapa":e,"cantidad":0,"monto_total":0,"monto_ponderado":0}) for e in ETAPAS],"abiertas":{"cantidad":t["c"],"monto_total":t["m"]}}

def actividades_pendientes():
    con=get_db();c=_cur(con)
    c.execute("SELECT a.*,TRIM(cl.nombre||' '||COALESCE(cl.apellidos,'')) AS cliente,cl.empresa FROM actividades a JOIN clientes cl ON cl.id=a.cliente_id WHERE a.completada=0 AND a.proxima_accion IS NOT NULL ORDER BY a.proxima_fecha")
    r=[dict(x) for x in c.fetchall()];c.close();con.close();return r

def crear_cliente(datos):
    tipo=datos.get("tipo") if datos.get("tipo") in TIPOS_CLIENTE else "Cliente potencial"
    con=get_db();c=con.cursor()
    c.execute("INSERT INTO clientes(nombre,apellidos,empresa,correo,telefono,rubro,origen,notas,tipo) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (datos["nombre"],datos.get("apellidos",""),datos.get("empresa"),datos.get("correo"),datos.get("telefono"),datos.get("rubro"),datos.get("origen"),datos.get("notas"),tipo))
    nid=c.fetchone()[0];con.commit();c.close();con.close();return nid

def actualizar_cliente(cliente_id,datos):
    if "tipo" in datos and datos["tipo"] not in TIPOS_CLIENTE:datos={k:v for k,v in datos.items() if k!="tipo"}
    campos=[x for x in("nombre","apellidos","empresa","correo","telefono","rubro","origen","notas","tipo") if x in datos]
    if not campos:return existe_cliente(cliente_id)
    con=get_db();c=con.cursor()
    c.execute(f"UPDATE clientes SET {','.join(f'{x}=%s' for x in campos)} WHERE id=%s",[datos[x] for x in campos]+[cliente_id])
    con.commit();ok=c.rowcount>0;c.close();con.close();return ok

def existe_cliente(cliente_id):
    con=get_db();c=con.cursor();c.execute("SELECT 1 FROM clientes WHERE id=%s",(cliente_id,));r=c.fetchone();c.close();con.close();return r is not None

def listar_proyectos(estado=None):
    con=get_db();c=_cur(con);sql="SELECT p.*,TRIM(cl.nombre||' '||COALESCE(cl.apellidos,'')) AS cliente,cl.empresa FROM proyectos p JOIN clientes cl ON cl.id=p.cliente_id"
    if estado:c.execute(sql+" WHERE p.estado=%s ORDER BY p.creado_en DESC",(estado,))
    else:c.execute(sql+" ORDER BY p.creado_en DESC")
    r=[dict(x) for x in c.fetchall()];c.close();con.close();return r

def crear_proyecto(datos):
    con=get_db();c=con.cursor()
    c.execute("INSERT INTO proyectos(cliente_id,nombre,descripcion,estado,fecha_inicio,fecha_fin) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
        (datos["cliente_id"],datos["nombre"],datos.get("descripcion"),datos.get("estado","Planificado"),datos.get("fecha_inicio"),datos.get("fecha_fin")))
    nid=c.fetchone()[0];con.commit();c.close();con.close();return nid

def actualizar_proyecto(proyecto_id,datos):
    campos=[x for x in("nombre","descripcion","estado","fecha_inicio","fecha_fin","cliente_id") if x in datos]
    if not campos:return False
    con=get_db();c=con.cursor()
    c.execute(f"UPDATE proyectos SET {','.join(f'{x}=%s' for x in campos)} WHERE id=%s",[datos[x] for x in campos]+[proyecto_id])
    con.commit();ok=c.rowcount>0;c.close();con.close();return ok

def registrar_accion_chatbot(accion,herramienta=None,detalle=None):
    con=get_db();c=con.cursor();c.execute("INSERT INTO acciones_chatbot(accion,herramienta,detalle) VALUES(%s,%s,%s)",(accion,herramienta,detalle));con.commit();c.close();con.close()

def listar_acciones_chatbot(limite=100):
    con=get_db();c=_cur(con);c.execute("SELECT * FROM acciones_chatbot ORDER BY id DESC LIMIT %s",(limite,));r=[dict(x) for x in c.fetchall()];c.close();con.close();return r

def crear_oportunidad(datos):
    con=get_db();c=con.cursor()
    c.execute("INSERT INTO oportunidades(cliente_id,descripcion,monto,etapa,probabilidad,cierre_estimado) VALUES(%s,%s,%s,%s,%s,%s)",
        (datos["cliente_id"],datos["descripcion"],datos.get("monto",0),datos.get("etapa","Prospecto"),datos.get("probabilidad",50),datos.get("cierre_estimado")))
    con.commit();c.close();con.close()

def cambiar_etapa(oportunidad_id,etapa):
    con=get_db();c=con.cursor();c.execute("UPDATE oportunidades SET etapa=%s WHERE id=%s",(etapa,oportunidad_id));con.commit();c.close();con.close()

def crear_actividad(datos):
    con=get_db();c=con.cursor()
    c.execute("INSERT INTO actividades(cliente_id,tipo,detalle,fecha,proxima_accion,proxima_fecha) VALUES(%s,%s,%s,CURRENT_DATE::TEXT,%s,%s)",
        (datos["cliente_id"],datos["tipo"],datos.get("detalle"),datos.get("proxima_accion"),datos.get("proxima_fecha")))
    con.commit();c.close();con.close()

def completar_actividad(actividad_id):
    con=get_db();c=con.cursor();c.execute("UPDATE actividades SET completada=1 WHERE id=%s",(actividad_id,));con.commit();c.close();con.close()
