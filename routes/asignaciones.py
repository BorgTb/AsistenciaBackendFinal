from flask import Blueprint, request, jsonify
from database import get_connection

asignaciones_bp = Blueprint('asignaciones', __name__)

@asignaciones_bp.route('/api/asignaciones', methods=['GET'])
def get_asignaciones():
    conn = get_connection()
    cur = conn.cursor()
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
def create_asignacion():
    data = request.json
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO asignaciones (persona_id, turno_id, vigente)
            VALUES (%s, %s, TRUE)
            RETURNING id
        """, (data['persona_id'], data['turno_id']))
        asig_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'ok': True, 'id': asig_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()