from flask import Blueprint, request, jsonify
from database import get_connection
from routes.auth import token_opcional, requiere_rol
import requests as http_requests
import secrets
import string
import hashlib

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
                   e.nombre as empresa_nombre,
                   d.password_hash, d.password_pendiente,
                   d.codigo_enrol
            FROM dispositivos d
            JOIN empresas e ON e.id = d.empresa_id
            ORDER BY d.id
        """)
    elif rol == 'empleador' and empresa_id:
        cur.execute("""
            SELECT d.id, d.empresa_id, d.nombre, d.mac_address, d.ip_local, d.estado,
                   d.ultimo_heartbeat, d.created_at, d.enrolado,
                   e.nombre as empresa_nombre,
                   d.password_hash, d.password_pendiente,
                   d.codigo_enrol
            FROM dispositivos d
            JOIN empresas e ON e.id = d.empresa_id
            WHERE d.empresa_id = %s
            ORDER BY d.id
        """, (empresa_id,))
    else:
        cur.execute("""
            SELECT d.id, d.empresa_id, d.nombre, d.mac_address, d.ip_local, d.estado,
                   d.ultimo_heartbeat, d.created_at, d.enrolado,
                   e.nombre as empresa_nombre,
                   d.password_hash, d.password_pendiente,
                   d.codigo_enrol
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
            'empresa_nombre': r[9],
            'tiene_password': r[10] is not None,
            'password_pendiente': r[11] if len(r) > 11 else False,
            'codigo_enrol': r[12] if len(r) > 12 else None
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
                    'enrolado': estado_data.get('enrolado', False),
                    'pin': estado_data.get('pin', '')
                }
            })
        return jsonify({'ok': False, 'error': f'HTTP {resp.status_code}'}), 200
    except http_requests.ConnectionError:
        return jsonify({'ok': False, 'error': 'No se pudo conectar al dispositivo'}), 200
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 200


@dispositivos_bp.route('/api/dispositivos/<dispositivo_id>/generar-password', methods=['POST'])
@requiere_rol('admin', 'empleador')
def generar_password_dispositivo(dispositivo_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute(
                "SELECT id, enrolado, mac_address, password_hash FROM dispositivos WHERE id::text = %s",
                (str(dispositivo_id),)
            )
        else:
            cur.execute(
                "SELECT id, enrolado, mac_address, password_hash FROM dispositivos WHERE id::text = %s AND empresa_id = %s",
                (str(dispositivo_id), request.empresa_id)
            )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404

        device_id, enrolado, mac_address, existing_hash = row

        if not enrolado or not mac_address:
            return jsonify({'error': 'Solo disponible para dispositivos enrolados'}), 400

        password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        cur.execute(
            "UPDATE dispositivos SET password_hash = %s, password_plain = %s, password_pendiente = TRUE WHERE id = %s",
            (password_hash, password, device_id)
        )
        conn.commit()
        return jsonify({'ok': True, 'password': password})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@dispositivos_bp.route('/api/dispositivos/<dispositivo_id>/password', methods=['DELETE'])
@requiere_rol('admin', 'empleador')
def eliminar_password_dispositivo(dispositivo_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute(
                "UPDATE dispositivos SET password_hash = NULL, password_plain = NULL, password_pendiente = FALSE WHERE id::text = %s RETURNING id",
                (str(dispositivo_id),)
            )
        else:
            cur.execute(
                "UPDATE dispositivos SET password_hash = NULL, password_plain = NULL, password_pendiente = FALSE WHERE id::text = %s AND empresa_id = %s RETURNING id",
                (str(dispositivo_id), request.empresa_id)
            )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        conn.commit()
        return jsonify({'ok': True, 'mensaje': 'Contraseña eliminada'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@dispositivos_bp.route('/api/dispositivos/check-password', methods=['GET'])
@token_opcional
def check_password_pendiente():
    mac = request.headers.get('X-Device-MAC', '')
    if not mac:
        return jsonify({'error': 'MAC requerida'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT password_pendiente, password_plain FROM dispositivos WHERE mac_address = %s",
            (mac,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404

        pendiente, password_plain = row
        if pendiente and password_plain:
            return jsonify({'pendiente': True, 'password': password_plain})
        return jsonify({'pendiente': False})
    finally:
        cur.close()
        conn.close()


@dispositivos_bp.route('/api/dispositivos/confirmar-password', methods=['POST'])
@token_opcional
def confirmar_password_aplicada():
    mac = request.headers.get('X-Device-MAC', '')
    if not mac:
        return jsonify({'error': 'MAC requerida'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE dispositivos SET password_pendiente = FALSE, password_plain = NULL WHERE mac_address = %s",
            (mac,)
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
