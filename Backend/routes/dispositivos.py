from flask import Blueprint, request, jsonify
from database import get_connection
from routes.auth import token_opcional, requiere_rol
import requests as http_requests

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


@dispositivos_bp.route('/api/dispositivos/<dispositivo_id>', methods=['DELETE'])
@requiere_rol('admin', 'empleador')
def delete_dispositivo(dispositivo_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute("DELETE FROM dispositivos WHERE id::text = %s", (str(dispositivo_id),))
        else:
            cur.execute(
                "DELETE FROM dispositivos WHERE id::text = %s AND empresa_id = %s",
                (str(dispositivo_id), request.empresa_id)
            )
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@dispositivos_bp.route('/api/dispositivos/<dispositivo_id>', methods=['PUT'])
@requiere_rol('admin', 'empleador')
def update_dispositivo(dispositivo_id):
    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'Nombre requerido'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute(
                "UPDATE dispositivos SET nombre = %s WHERE id::text = %s RETURNING id, nombre",
                (nombre, str(dispositivo_id))
            )
        else:
            cur.execute(
                "UPDATE dispositivos SET nombre = %s WHERE id::text = %s AND empresa_id = %s RETURNING id, nombre",
                (nombre, str(dispositivo_id), request.empresa_id)
            )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        conn.commit()
        return jsonify({'ok': True, 'id': str(row[0]), 'nombre': row[1]})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@dispositivos_bp.route('/api/dispositivos/verificar', methods=['POST'])
@requiere_rol('admin', 'empleador')
def verificar_dispositivo():
    data = request.json or {}
    ip = (data.get('ip') or '').strip()
    if not ip:
        return jsonify({'ok': False, 'error': 'IP requerida'}), 400

    try:
        resp = http_requests.get(f'http://{ip}/estado', timeout=5)
        if resp.status_code == 200:
            estado_data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
            return jsonify({
                'ok': True,
                'mensaje': 'Dispositivo responde correctamente',
                'datos': {
                    'mac': estado_data.get('mac', ''),
                    'ssid': estado_data.get('ssid', ''),
                    'enrolado': estado_data.get('enrolado', False)
                }
            })
        return jsonify({'ok': False, 'error': f'HTTP {resp.status_code}'}), 200
    except http_requests.ConnectionError:
        return jsonify({'ok': False, 'error': 'No se pudo conectar al dispositivo'}), 200
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 200
