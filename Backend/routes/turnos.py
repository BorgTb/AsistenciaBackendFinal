from flask import Blueprint, request, jsonify
from database import get_connection
from routes.auth import token_opcional


turnos_bp = Blueprint('turnos', __name__)


@turnos_bp.route('/api/turnos', methods=['GET'])
@token_opcional
def get_turnos():
    conn = get_connection()
    cur = conn.cursor()

    rol = request.user_rol
    empresa_id = request.empresa_id
    persona_id = request.persona_id

    if rol == 'admin':
        cur.execute("SELECT id, nombre, hora_inicio, hora_fin, dias, empresa_id FROM turnos ORDER BY id")
    elif rol == 'empleador' and empresa_id:
        cur.execute(
            "SELECT id, nombre, hora_inicio, hora_fin, dias, empresa_id FROM turnos WHERE empresa_id = %s ORDER BY id",
            (empresa_id,)
        )
    elif rol == 'trabajador' and persona_id:
        cur.execute(
            """SELECT t.id, t.nombre, t.hora_inicio, t.hora_fin, t.dias, t.empresa_id
               FROM turnos t
               JOIN asignaciones a ON a.turno_id = t.id AND a.vigente = TRUE
               WHERE a.persona_id = %s ORDER BY t.id""",
            (persona_id,)
        )
    else:
        if empresa_id:
            cur.execute(
                "SELECT id, nombre, hora_inicio, hora_fin, dias, empresa_id FROM turnos WHERE empresa_id = %s ORDER BY id",
                (empresa_id,)
            )
        else:
            cur.close()
            conn.close()
            return jsonify([])

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "id": r[0],
        "nombre": r[1],
        "inicio": str(r[2]),
        "fin": str(r[3]),
        "dias": r[4],
        "empresa_id": r[5]
    } for r in rows])


@turnos_bp.route('/api/turnos', methods=['POST'])
@token_opcional
def create_turno():
    data = request.json
    if not request.empresa_id:
        return jsonify({'error': 'No autorizado: empresa no identificada'}), 401
    empresa_id = request.empresa_id
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO turnos (empresa_id, nombre, hora_inicio, hora_fin, dias) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (empresa_id, data['nombre'], data['inicio'], data['fin'], data.get('dias', ''))
        )
        turno_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'ok': True, 'id': turno_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@turnos_bp.route('/api/turnos/<turno_id>', methods=['DELETE'])
@token_opcional
def delete_turno(turno_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.empresa_id and request.user_rol != 'admin':
            cur.execute(
                "DELETE FROM turnos WHERE id::text = %s AND empresa_id = %s",
                (str(turno_id), request.empresa_id)
            )
        else:
            cur.execute("DELETE FROM turnos WHERE id::text = %s", (str(turno_id),))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
