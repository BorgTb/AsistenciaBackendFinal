from flask import Blueprint, request, jsonify
from database import get_connection
from routes.auth import token_opcional, requiere_rol
import requests as http_requests
import secrets
import string
import hashlib
import json

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
                   d.codigo_enrol,
                   d.con_colacion, d.colacion_inicio, d.colacion_fin
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
                   d.codigo_enrol,
                   d.con_colacion, d.colacion_inicio, d.colacion_fin
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
                   d.codigo_enrol,
                   d.con_colacion, d.colacion_inicio, d.colacion_fin
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
            'codigo_enrol': r[12] if len(r) > 12 else None,
            'con_colacion': r[13] if len(r) > 13 else False,
            'colacion_inicio': str(r[14]) if len(r) > 14 and r[14] else None,
            'colacion_fin': str(r[15]) if len(r) > 15 and r[15] else None
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
    conn = get_connection()
    cur = conn.cursor()
    try:
        updates = []
        params = []

        if 'nombre' in data:
            nombre = (data['nombre'] or '').strip()
            if not nombre:
                return jsonify({'error': 'Nombre requerido'}), 400
            updates.append("nombre = %s")
            params.append(nombre)

        if 'con_colacion' in data:
            updates.append("con_colacion = %s")
            params.append(data['con_colacion'])

        if 'colacion_inicio' in data:
            updates.append("colacion_inicio = %s")
            params.append(data.get('colacion_inicio') or None)

        if 'colacion_fin' in data:
            updates.append("colacion_fin = %s")
            params.append(data.get('colacion_fin') or None)

        if not updates:
            return jsonify({'error': 'Sin campos para actualizar'}), 400

        where = "id::text = %s"
        params.append(str(dispositivo_id))

        if request.user_rol != 'admin':
            where += " AND empresa_id = %s"
            params.append(request.empresa_id)

        cur.execute(
            f"UPDATE dispositivos SET {', '.join(updates)} WHERE {where} RETURNING id, nombre",
            params
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


@dispositivos_bp.route('/api/dispositivos/<dispositivo_id>/registrar-huella', methods=['POST'])
@requiere_rol('admin', 'empleador')
def registrar_huella(dispositivo_id):
    data = request.json or {}
    persona_id = data.get('persona_id')
    if not persona_id:
        return jsonify({'error': 'Se requiere persona_id'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT REPLACE(mac_address, ':', '') as mac, empresa_id FROM dispositivos WHERE id::text = %s",
            (str(dispositivo_id),)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        mac, device_empresa_id = row

        if request.user_rol != 'admin' and device_empresa_id != request.empresa_id:
            return jsonify({'error': 'Dispositivo no pertenece a tu empresa'}), 403

        cur.execute(
            "SELECT id FROM personas WHERE id = %s AND empresa_id = %s",
            (persona_id, device_empresa_id)
        )
        if not cur.fetchone():
            return jsonify({'error': 'Persona no encontrada en esta empresa'}), 404
    finally:
        cur.close()
        conn.close()

    try:
        from mqtt_handler import _mqtt_client
        if _mqtt_client is None:
            return jsonify({'error': 'MQTT no disponible'}), 503

        topic = f"backend/huella/registrar/{mac}"
        payload = json.dumps({"persona_id": str(persona_id), "accion": "registrar"})
        _mqtt_client.publish(topic, payload)

        return jsonify({
            'ok': True,
            'mensaje': 'Solicitud de registro de huella enviada al dispositivo',
            'dispositivo_id': dispositivo_id,
            'persona_id': str(persona_id)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dispositivos_bp.route('/api/dispositivos/<dispositivo_id>/reiniciar', methods=['POST'])
@requiere_rol('admin', 'empleador')
def reiniciar_dispositivo(dispositivo_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute(
                "SELECT REPLACE(mac_address, ':', '') as mac, nombre, empresa_id FROM dispositivos WHERE id::text = %s",
                (str(dispositivo_id),)
            )
        else:
            cur.execute(
                "SELECT REPLACE(mac_address, ':', '') as mac, nombre, empresa_id FROM dispositivos WHERE id::text = %s AND empresa_id = %s",
                (str(dispositivo_id), request.empresa_id)
            )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        mac, nombre, device_empresa_id = row

        if request.user_rol != 'admin' and device_empresa_id != request.empresa_id:
            return jsonify({'error': 'Dispositivo no pertenece a tu empresa'}), 403
    finally:
        cur.close()
        conn.close()

    try:
        from mqtt_handler import enviar_comando_dispositivo
        if enviar_comando_dispositivo(mac, 'reiniciar'):
            return jsonify({'ok': True, 'mensaje': f'Comando de reinicio enviado a {nombre}'})
        else:
            return jsonify({'error': 'MQTT no disponible'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dispositivos_bp.route('/api/dispositivos/sync', methods=['POST'])
@requiere_rol('admin', 'empleador')
def sync_dispositivos():
    empresa_id = request.empresa_id

    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute(
                "SELECT REPLACE(mac_address, ':', '') as mac, nombre FROM dispositivos WHERE enrolado = TRUE AND mac_address IS NOT NULL AND mac_address != ''"
            )
        elif empresa_id:
            cur.execute(
                "SELECT REPLACE(mac_address, ':', '') as mac, nombre FROM dispositivos WHERE empresa_id = %s AND enrolado = TRUE AND mac_address IS NOT NULL AND mac_address != ''",
                (empresa_id,)
            )
        else:
            return jsonify({'error': 'No autorizado'}), 401

        dispositivos = cur.fetchall()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

    if not dispositivos:
        return jsonify({'ok': False, 'mensaje': 'No hay dispositivos enrolados'}), 200

    try:
        from mqtt_handler import enviar_comando_dispositivo
        enviados = 0
        for mac, nombre in dispositivos:
            if enviar_comando_dispositivo(mac, 'sync'):
                enviados += 1

        return jsonify({
            'ok': True,
            'mensaje': f'Comando de sincronizacion enviado a {enviados}/{len(dispositivos)} dispositivo(s)'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dispositivos_bp.route('/api/dispositivos/<dispositivo_id>/wifi-reconnect', methods=['POST'])
@requiere_rol('admin', 'empleador')
def reconectar_wifi_dispositivo(dispositivo_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute(
                "SELECT REPLACE(mac_address, ':', '') as mac, nombre, empresa_id FROM dispositivos WHERE id::text = %s",
                (str(dispositivo_id),)
            )
        else:
            cur.execute(
                "SELECT REPLACE(mac_address, ':', '') as mac, nombre, empresa_id FROM dispositivos WHERE id::text = %s AND empresa_id = %s",
                (str(dispositivo_id), request.empresa_id)
            )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        mac, nombre, device_empresa_id = row

        if request.user_rol != 'admin' and device_empresa_id != request.empresa_id:
            return jsonify({'error': 'Dispositivo no pertenece a tu empresa'}), 403
    finally:
        cur.close()
        conn.close()

    try:
        from mqtt_handler import enviar_comando_dispositivo
        if enviar_comando_dispositivo(mac, 'wifi-reconnect'):
            return jsonify({'ok': True, 'mensaje': f'Comando de reconexion WiFi enviado a {nombre}'})
        else:
            return jsonify({'error': 'MQTT no disponible'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500
