from flask import Blueprint, jsonify
from database import get_connection
from routes.auth import requiere_rol, requiere_login

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/api/logs', methods=['GET'])
@requiere_rol('admin', 'empleador')
def get_logs():
    conn = get_connection()
    cur = conn.cursor()

    rol = request.user_rol
    empresa_id = request.empresa_id

    if rol == 'admin':
        cur.execute("""
            SELECT s.id, s.dispositivo_id, s.registros_enviados, s.registros_ok,
                   s.estado, s.detalle, s.fecha
            FROM sincronizacion_log s
            ORDER BY s.fecha DESC, s.id DESC
            LIMIT 200
        """)
    else:
        cur.execute("""
            SELECT s.id, s.dispositivo_id, s.registros_enviados, s.registros_ok,
                   s.estado, s.detalle, s.fecha
            FROM sincronizacion_log s
            JOIN dispositivos d ON d.id = s.dispositivo_id
            WHERE d.empresa_id = %s
            ORDER BY s.fecha DESC, s.id DESC
            LIMIT 200
        """, (empresa_id,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            'id': str(r[0]),
            'dispositivo_id': str(r[1]) if r[1] is not None else None,
            'registros_enviados': r[2],
            'registros_ok': r[3],
            'estado': r[4],
            'detalle': r[5],
            'fecha': str(r[6]) if r[6] else None,
        }
        for r in rows
    ])


@logs_bp.route('/api/logs', methods=['DELETE'])
@requiere_rol('admin', 'empleador')
def clear_logs():
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute('TRUNCATE TABLE sincronizacion_log RESTART IDENTITY')
        else:
            cur.execute(
                "DELETE FROM sincronizacion_log WHERE dispositivo_id IN (SELECT id FROM dispositivos WHERE empresa_id = %s)",
                (request.empresa_id,)
            )
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
