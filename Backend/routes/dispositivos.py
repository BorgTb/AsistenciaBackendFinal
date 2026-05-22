from flask import Blueprint, jsonify
from database import get_connection

dispositivos_bp = Blueprint('dispositivos', __name__)


@dispositivos_bp.route('/api/dispositivos', methods=['GET'])
def get_dispositivos():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, empresa_id, nombre, mac_address, ip_local, estado, ultimo_heartbeat, created_at
        FROM dispositivos
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            'id': str(r[0]),
            'empresa_id': str(r[1]) if r[1] is not None else None,
            'nombre': r[2],
            'mac_address': r[3],
            'ip_local': r[4],
            'estado': r[5],
            'ultimo_heartbeat': str(r[6]) if r[6] else None,
            'created_at': str(r[7]) if r[7] else None,
        }
        for r in rows
    ])