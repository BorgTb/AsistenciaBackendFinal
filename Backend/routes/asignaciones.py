from flask import Blueprint, request, jsonify
from database import get_connection
from routes.auth import token_opcional, requiere_rol


asignaciones_bp = Blueprint('asignaciones', __name__)


@asignaciones_bp.route('/api/asignaciones', methods=['GET'])
@token_opcional
def get_asignaciones():
    conn = get_connection()
    cur = conn.cursor()

    rol = request.user_rol
    empresa_id = request.empresa_id
    persona_id = request.persona_id

    if rol == 'admin':
        cur.execute("""
            SELECT a.id, a.persona_id, p.nombre, a.turno_id, t.nombre,
                   a.fecha_asignacion, a.vigente
            FROM asignaciones a
            JOIN personas p ON a.persona_id = p.id
            JOIN turnos t ON a.turno_id = t.id
            ORDER BY a.id
        """)
    elif rol == 'empleador' and empresa_id:
        cur.execute("""
            SELECT a.id, a.persona_id, p.nombre, a.turno_id, t.nombre,
                   a.fecha_asignacion, a.vigente
            FROM asignaciones a
            JOIN personas p ON a.persona_id = p.id AND p.empresa_id = %s
            JOIN turnos t ON a.turno_id = t.id
            ORDER BY a.id
        """, (empresa_id,))
    elif rol == 'trabajador' and persona_id:
        cur.execute("""
            SELECT a.id, a.persona_id, p.nombre, a.turno_id, t.nombre,
                   a.fecha_asignacion, a.vigente
            FROM asignaciones a
            JOIN personas p ON a.persona_id = p.id
            JOIN turnos t ON a.turno_id = t.id
            WHERE a.persona_id = %s
            ORDER BY a.id
        """, (persona_id,))
    else:
        cur.execute("""
            SELECT a.id, a.persona_id, p.nombre, a.turno_id, t.nombre,
                   a.fecha_asignacion, a.vigente
            FROM asignaciones a
            JOIN personas p ON a.persona_id = p.id
            JOIN turnos t ON a.turno_id = t.id
            ORDER BY a.id
        """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "id": r[0],
        "persona_id": r[1],
        "persona_nombre": r[2],
        "turno_id": r[3],
        "turno_nombre": r[4],
        "fecha_asignacion": str(r[5]),
        "vigente": r[6]
    } for r in rows])


@asignaciones_bp.route('/api/asignaciones', methods=['POST'])
@token_opcional
def create_asignacion():
    data = request.json
    empresa_id = request.empresa_id

    conn = get_connection()
    cur = conn.cursor()
    try:
        if empresa_id and request.user_rol != 'admin':
            cur.execute(
                "SELECT id FROM personas WHERE id = %s AND empresa_id = %s",
                (data['persona_id'], empresa_id)
            )
            if not cur.fetchone():
                return jsonify({'error': 'Persona no pertenece a tu empresa'}), 403

        cur.execute(
            "INSERT INTO asignaciones (persona_id, turno_id, vigente) VALUES (%s, %s, TRUE) RETURNING id",
            (data['persona_id'], data['turno_id'])
        )
        asig_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'ok': True, 'id': asig_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@asignaciones_bp.route('/api/asignaciones/<asignacion_id>', methods=['DELETE'])
@token_opcional
def delete_asignacion(asignacion_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.empresa_id and request.user_rol != 'admin':
            cur.execute(
                """DELETE FROM asignaciones a
                   USING personas p
                   WHERE a.id::text = %s AND a.persona_id = p.id AND p.empresa_id = %s""",
                (str(asignacion_id), request.empresa_id)
            )
        else:
            cur.execute("DELETE FROM asignaciones WHERE id::text = %s", (str(asignacion_id),))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
