from flask import Blueprint, jsonify
from database import get_connection
from routes.auth import token_opcional

dispositivos_bp = Blueprint('dispositivos', __name__)


@dispositivos_bp.route('/api/dispositivos', methods=['GET'])
@token_opcional
def get_dispositivos():
    conn = get_connection()
    cur = conn.cursor()

    rol = request.user_rol
    empresa_id = request.empresa_id

    if rol == 'admin':
        cur.execute("""
            SELECT d.id, d.empresa_id, d.nombre, d.mac_address, d.ip_local, d.estado,
                   d.ultimo_heartbeat, d.created_at, d.enrolado,
                   e.nombre as empresa_nombre
            FROM dispositivos d
            JOIN empresas e ON e.id = d.empresa_id
            ORDER BY d.id
        """)
    elif rol == 'empleador' and empresa_id:
        cur.execute("""
            SELECT d.id, d.empresa_id, d.nombre, d.mac_address, d.ip_local, d.estado,
                   d.ultimo_heartbeat, d.created_at, d.enrolado,
                   e.nombre as empresa_nombre
            FROM dispositivos d
            JOIN empresas e ON e.id = d.empresa_id
            WHERE d.empresa_id = %s
            ORDER BY d.id
        """, (empresa_id,))
    else:
        cur.execute("""
            SELECT d.id, d.empresa_id, d.nombre, d.mac_address, d.ip_local, d.estado,
                   d.ultimo_heartbeat, d.created_at, d.enrolado,
                   e.nombre as empresa_nombre
            FROM dispositivos d
            JOIN empresas e ON e.id = d.empresa_id
            ORDER BY d.id
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
            'enrolado': r[8],
            'empresa_nombre': r[9]
        }
        for r in rows
    ])
