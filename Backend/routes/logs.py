from flask import Blueprint, jsonify
from database import get_connection

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/api/logs', methods=['GET'])
def get_logs():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, dispositivo_id, registros_enviados, registros_ok, estado, detalle, fecha
        FROM sincronizacion_log
        ORDER BY fecha DESC, id DESC
        LIMIT 200
    """)
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
def clear_logs():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('TRUNCATE TABLE sincronizacion_log RESTART IDENTITY')
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()