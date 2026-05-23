from flask import Blueprint, request, jsonify
from database import get_connection
from routes.auth import token_opcional

asistencias_bp = Blueprint('asistencias', __name__)


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
        cur.execute(
            "INSERT INTO asistencias (persona_id, dispositivo_id, nombre, tipo, metodo, origen, sincronizado) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (persona_id, dispositivo_id, data.get('nombre'), data.get('tipo'), data.get('metodo', 'huella'), data.get('origen', 'dispositivo'), data.get('sincronizado', False))
        )
        asist_id = cur.fetchone()[0]
        conn.commit()
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
            cur.execute("""
                SELECT id FROM asistencias
                WHERE persona_id = %s AND tipo = %s
                AND ABS(EXTRACT(EPOCH FROM (fecha_hora - NOW()))) < 60
            """, (r.get('persona_id'), r.get('tipo')))

            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO asistencias (persona_id, nombre, tipo, metodo, origen, sincronizado) VALUES (%s, %s, %s, %s, 'sync', TRUE)",
                    (r.get('persona_id'), r.get('nombre'), r.get('tipo'), r.get('metodo', 'huella'))
                )
                insertados += 1
        except:
            errores += 1

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True, 'insertados': insertados, 'errores': errores})
