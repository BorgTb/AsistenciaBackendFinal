from flask import Blueprint, request, jsonify
from database import get_connection

turnos_bp = Blueprint('turnos', __name__)

@turnos_bp.route('/api/turnos', methods=['GET'])
def get_turnos():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, hora_inicio, hora_fin, dias FROM turnos ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "id": r[0],
        "nombre": r[1],
        "inicio": str(r[2]),
        "fin": str(r[3]),
        "dias": r[4]
    } for r in rows])


@turnos_bp.route('/api/turnos', methods=['POST'])
def create_turno():
    data = request.json
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO turnos (nombre, hora_inicio, hora_fin, dias)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            data['nombre'],
            data['inicio'],
            data['fin'],
            data.get('dias', '')
        ))
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
def delete_turno(turno_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM turnos WHERE id::text = %s", (str(turno_id),))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()