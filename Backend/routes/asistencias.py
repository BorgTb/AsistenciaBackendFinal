from flask import Blueprint, request, jsonify
from database import get_connection
from routes.auth import token_opcional
import threading

asistencias_bp = Blueprint('asistencias', __name__)


def _erp_push_async(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id):
    try:
        from routes.erp import enviar_asistencia_a_erps
        enviar_asistencia_a_erps(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id)
    except Exception:
        pass


def _disparar_erp_push(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id):
    if not empresa_id:
        return
    t = threading.Thread(target=_erp_push_async, args=(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id))
    t.daemon = True
    t.start()


@asistencias_bp.route('/api/asistencias', methods=['GET'])
@token_opcional
def get_asistencias():
    conn = get_connection()
    cur = conn.cursor()

    rol = request.user_rol
    empresa_id = request.empresa_id
    persona_id = request.persona_id

    if rol == 'admin':
        cur.execute("""
            SELECT a.id, a.persona_id, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.origen, a.sincronizado, a.dispositivo_id
            FROM asistencias a
            ORDER BY a.fecha_hora DESC
            LIMIT 500
        """)
    elif rol == 'empleador' and empresa_id:
        cur.execute("""
            SELECT a.id, a.persona_id, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.origen, a.sincronizado, a.dispositivo_id
            FROM asistencias a
            JOIN personas p ON a.persona_id = p.id
            WHERE p.empresa_id = %s
            ORDER BY a.fecha_hora DESC
            LIMIT 500
        """, (empresa_id,))
    elif rol == 'trabajador' and persona_id:
        cur.execute("""
            SELECT a.id, a.persona_id, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.origen, a.sincronizado, a.dispositivo_id
            FROM asistencias a
            WHERE a.persona_id = %s
            ORDER BY a.fecha_hora DESC
            LIMIT 200
        """, (persona_id,))
    else:
        cur.execute("""
            SELECT a.id, a.persona_id, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.origen, a.sincronizado, a.dispositivo_id
            FROM asistencias a
            ORDER BY a.fecha_hora DESC
            LIMIT 500
        """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "id": r[0],
        "persona_id": r[1],
        "nombre": r[2],
        "tipo": r[3],
        "metodo": r[4],
        "fecha_hora": str(r[5]),
        "origen": r[6],
        "sincronizado": r[7],
        "dispositivo_id": r[8]
    } for r in rows])


@asistencias_bp.route('/api/asistencias', methods=['POST'])
def create_asistencia():
    data = request.json
    conn = get_connection()
    cur = conn.cursor()
    try:
        dispositivo_id = data.get('dispositivo_id') or 1
        persona_id = data.get('persona_id')
        nombre = data.get('nombre')
        tipo = data.get('tipo')
        metodo = data.get('metodo', 'huella')

        cur.execute(
            "INSERT INTO asistencias (persona_id, dispositivo_id, nombre, tipo, metodo, origen, sincronizado) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, fecha_hora",
            (persona_id, dispositivo_id, nombre, tipo, metodo, data.get('origen', 'dispositivo'), data.get('sincronizado', False))
        )
        row = cur.fetchone()
        asist_id = row[0]
        fecha_hora = row[1]
        conn.commit()

        empresa_id = None
        if persona_id:
            cur.execute("SELECT empresa_id FROM personas WHERE id = %s", (persona_id,))
            emp_row = cur.fetchone()
            if emp_row:
                empresa_id = emp_row[0]

        _disparar_erp_push(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id)

        return jsonify({'ok': True, 'id': asist_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@asistencias_bp.route('/api/asistencias/sync', methods=['POST'])
def sync_asistencias():
    data = request.json
    registros = data.get('registros', [])
    conn = get_connection()
    cur = conn.cursor()
    insertados = 0
    errores = 0

    for r in registros:
        try:
            persona_id_buscar = r.get('persona_id')
            tipo_buscar = r.get('tipo')
            cur.execute("""
                SELECT id FROM asistencias
                WHERE persona_id = %s AND tipo = %s
                AND ABS(EXTRACT(EPOCH FROM (fecha_hora - NOW()))) < 60
            """, (persona_id_buscar, tipo_buscar))

            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO asistencias (persona_id, nombre, tipo, metodo, origen, sincronizado) VALUES (%s, %s, %s, %s, 'sync', TRUE) RETURNING id, fecha_hora",
                    (persona_id_buscar, r.get('nombre'), tipo_buscar, r.get('metodo', 'huella'))
                )
                row = cur.fetchone()
                insertados += 1

                empresa_id = None
                if persona_id_buscar:
                    cur.execute("SELECT empresa_id FROM personas WHERE id = %s", (persona_id_buscar,))
                    emp_row = cur.fetchone()
                    if emp_row:
                        empresa_id = emp_row[0]

                _disparar_erp_push(
                    persona_id_buscar, r.get('nombre'), tipo_buscar,
                    r.get('metodo', 'huella'), row[1], empresa_id
                )
        except:
            errores += 1

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True, 'insertados': insertados, 'errores': errores})
