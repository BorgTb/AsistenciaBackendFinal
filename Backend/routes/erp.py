import json
import traceback
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

import requests
from flask import Blueprint, jsonify, request
from database import get_connection, resolver_rut_a_id
from routes.auth import requiere_rol, token_opcional

CHILE_TZ = timezone.utc  # fallback
if ZoneInfo:
    try:
        CHILE_TZ = ZoneInfo('America/Santiago')
    except Exception:
        pass

erp_bp = Blueprint('erp', __name__)


def _transformar_datos(datos_originales, field_map_json):
    if not field_map_json or field_map_json == '{}':
        return dict(datos_originales)
    try:
        field_map = json.loads(field_map_json) if isinstance(field_map_json, str) else field_map_json
    except Exception:
        return dict(datos_originales)
    resultado = {}
    for clave_origen, clave_destino in field_map.items():
        valor = datos_originales.get(clave_origen, datos_originales.get(clave_destino))
        if valor is not None:
            resultado[clave_destino] = valor
    for k, v in datos_originales.items():
        if k not in field_map:
            resultado[k] = v
    return resultado


def _enviar_a_webhook(webhook_url, headers_json, payload, timeout=10):
    headers = {}
    if headers_json and headers_json != '{}':
        try:
            headers = json.loads(headers_json) if isinstance(headers_json, str) else headers_json
        except Exception:
            headers = {'Content-Type': 'application/json'}
    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json'
    try:
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=timeout)
        return {'ok': resp.ok, 'status_code': resp.status_code, 'respuesta': resp.text[:500]}
    except requests.ConnectionError:
        return {'ok': False, 'error': 'No se pudo conectar al endpoint ERP'}
    except requests.Timeout:
        return {'ok': False, 'error': 'Timeout al contactar ERP'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _fmt_chile(dt):
    if not dt:
        return ''
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHILE_TZ).strftime('%Y-%m-%dT%H:%M:%S%z')


def enviar_asistencia_a_erps(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT id, webhook_url, headers, field_map
               FROM integraciones_erp
               WHERE empresa_id = %s AND activo = TRUE AND envio_auto = TRUE""",
            (empresa_id,)
        )
        erps = cur.fetchall()
        rut = None
        if persona_id:
            cur.execute("SELECT rut FROM personas WHERE id = %s", (persona_id,))
            row = cur.fetchone()
            if row:
                rut = row[0]
    finally:
        cur.close()
        conn.close()

    datos = {
        'rut': rut or '',
        'nombre': nombre or '',
        'tipo': tipo or '',
        'metodo': metodo or '',
        'fecha_hora': _fmt_chile(fecha_hora),
        'timestamp': datetime.now(CHILE_TZ).strftime('%Y-%m-%dT%H:%M:%S%z'),
    }

    resultados = []
    for erp_id, webhook_url, headers_json, field_map_json in erps:
        payload = _transformar_datos(datos, field_map_json)
        resultado = _enviar_a_webhook(webhook_url, headers_json, payload)
        _guardar_estado_envio(erp_id, resultado)
        resultados.append({'erp_id': erp_id, 'resultado': resultado})
    return resultados


def _guardar_estado_envio(erp_id, resultado):
    conn = get_connection()
    cur = conn.cursor()
    try:
        estado = 'ok' if resultado.get('ok') else 'error: ' + str(resultado.get('error', resultado.get('status_code', 'desconocido')))[:195]
        cur.execute(
            "UPDATE integraciones_erp SET ultimo_envio = NOW(), ultimo_estado = %s WHERE id = %s",
            (estado, erp_id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()
        conn.close()


@erp_bp.route('/api/erp', methods=['GET'])
@requiere_rol('admin', 'empleador')
def get_erp():
    conn = get_connection()
    cur = conn.cursor()

    rol = request.user_rol
    empresa_id = request.empresa_id

    if rol == 'admin':
        cur.execute("""
            SELECT id, nombre, tipo, webhook_url, headers, field_map, envio_auto, activo,
                   ultimo_envio, ultimo_estado, created_at
            FROM integraciones_erp
            ORDER BY id
        """)
    else:
        cur.execute("""
            SELECT id, nombre, tipo, webhook_url, headers, field_map, envio_auto, activo,
                   ultimo_envio, ultimo_estado, created_at
            FROM integraciones_erp
            WHERE empresa_id = %s
            ORDER BY id
        """, (empresa_id,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            'id': str(r[0]),
            'nombre': r[1],
            'tipo': r[2],
            'webhookUrl': r[3],
            'headers': r[4] or '{}',
            'fieldMap': r[5] or '{}',
            'envioAuto': r[6],
            'activo': r[7],
            'ultimoEnvio': str(r[8]) if r[8] else None,
            'ultimoEstado': r[9] or '',
            'createdAt': str(r[10]) if r[10] else None,
        }
        for r in rows
    ])


@erp_bp.route('/api/erp', methods=['POST'])
@requiere_rol('admin', 'empleador')
def create_erp():
    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    tipo = (data.get('tipo') or 'generic').strip()
    webhook_url = (data.get('webhook_url') or data.get('webhookUrl') or '').strip()

    if not nombre or not webhook_url:
        return jsonify({'error': 'Faltan datos'}), 400

    headers = data.get('headers', '{}')
    field_map = data.get('field_map', data.get('fieldMap', '{}'))
    envio_auto = bool(data.get('envio_auto', data.get('envioAuto', True)))
    activo = bool(data.get('activo', True))
    empresa_id = request.empresa_id
    if not empresa_id:
        return jsonify({'error': 'No autorizado: empresa no identificada'}), 401

    if isinstance(headers, dict):
        headers = json.dumps(headers, ensure_ascii=False)
    if isinstance(field_map, dict):
        field_map = json.dumps(field_map, ensure_ascii=False)

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO integraciones_erp (empresa_id, nombre, tipo, webhook_url, headers, field_map, envio_auto, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (empresa_id, nombre, tipo, webhook_url, str(headers), str(field_map), envio_auto, activo)
        )
        erp_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'ok': True, 'id': erp_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@erp_bp.route('/api/erp/<erp_id>', methods=['DELETE'])
@requiere_rol('admin', 'empleador')
def delete_erp(erp_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol != 'admin':
            cur.execute(
                "DELETE FROM integraciones_erp WHERE id::text = %s AND empresa_id = %s",
                (str(erp_id), request.empresa_id)
            )
        else:
            cur.execute('DELETE FROM integraciones_erp WHERE id::text = %s', (str(erp_id),))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@erp_bp.route('/api/erp/<erp_id>/test', methods=['POST'])
@requiere_rol('admin', 'empleador')
def test_erp(erp_id):
    conn = get_connection()
    cur = conn.cursor()

    if request.user_rol != 'admin':
        cur.execute(
            "SELECT empresa_id FROM integraciones_erp WHERE id::text = %s",
            (str(erp_id),)
        )
        row_check = cur.fetchone()
        if not row_check or row_check[0] != request.empresa_id:
            cur.close()
            conn.close()
            return jsonify({'ok': False, 'mensaje': 'Integración no encontrada'}), 404

    cur.execute(
        "SELECT nombre, tipo, webhook_url, headers, field_map, envio_auto, activo FROM integraciones_erp WHERE id::text = %s",
        (str(erp_id),)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'mensaje': 'Integración no encontrada'}), 404

    nombre, tipo, webhook_url, headers_text, field_map_text, envio_auto, activo = row

    if not activo:
        return jsonify({'ok': False, 'mensaje': 'La integración está inactiva'}), 400

    payload = {
        'rut': '11.111.111-1',
        'nombre': 'Test Usuario',
        'tipo': 'entrada',
        'metodo': 'test',
        'fecha_hora': datetime.now(CHILE_TZ).strftime('%Y-%m-%dT%H:%M:%S%z'),
    }
    transformed = _transformar_datos(payload, field_map_text)
    resultado = _enviar_a_webhook(webhook_url, headers_text, transformed)
    _guardar_estado_envio(erp_id, resultado)

    return jsonify({
        'ok': resultado.get('ok', False),
        'status_code': resultado.get('status_code'),
        'mensaje': 'Test ejecutado',
        'respuesta': resultado.get('respuesta', resultado.get('error', ''))
    })


@erp_bp.route('/api/erp/<erp_id>/enviar', methods=['POST'])
@requiere_rol('admin', 'empleador')
def enviar_erp(erp_id):
    conn = get_connection()
    cur = conn.cursor()

    if request.user_rol != 'admin':
        cur.execute(
            "SELECT empresa_id FROM integraciones_erp WHERE id::text = %s",
            (str(erp_id),)
        )
        row_check = cur.fetchone()
        if not row_check or row_check[0] != request.empresa_id:
            cur.close()
            conn.close()
            return jsonify({'ok': False, 'mensaje': 'Integración no encontrada'}), 404

    cur.execute(
        "SELECT webhook_url, headers, field_map, envio_auto, activo, empresa_id FROM integraciones_erp WHERE id::text = %s",
        (str(erp_id),)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({'ok': False, 'mensaje': 'Integración no encontrada'}), 404

    webhook_url, headers_text, field_map_text, envio_auto, activo, empresa_id = row

    if not activo:
        return jsonify({'ok': False, 'mensaje': 'La integración está inactiva'}), 400

    cur.execute("""
        SELECT a.persona_id, p.rut, a.nombre, a.tipo, a.metodo, a.fecha_hora
        FROM asistencias a
        JOIN personas p ON a.persona_id = p.id
        WHERE p.empresa_id = %s
        ORDER BY a.fecha_hora DESC
        LIMIT 200
    """, (empresa_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return jsonify({'ok': True, 'mensaje': 'Sin asistencias para enviar', 'enviados': 0})

    enviados = 0
    errores = 0
    ultimo_resultado = None

    for persona_id, rut, nombre, tipo, metodo, fecha_hora in rows:
        datos = {
            'rut': rut or '',
            'nombre': nombre or '',
            'tipo': tipo or '',
            'metodo': metodo or '',
            'fecha_hora': _fmt_chile(fecha_hora),
        }
        payload = _transformar_datos(datos, field_map_text)
        resultado = _enviar_a_webhook(webhook_url, headers_text, payload)
        ultimo_resultado = resultado
        if resultado.get('ok'):
            enviados += 1
        else:
            errores += 1

    _guardar_estado_envio(erp_id, ultimo_resultado or {'ok': False, 'error': 'sin datos'})

    return jsonify({
        'ok': True,
        'enviados': enviados,
        'errores': errores,
        'ultimo_estado': ultimo_resultado
    })


@erp_bp.route('/api/erp/<erp_id>/estado', methods=['GET'])
@requiere_rol('admin', 'empleador')
def estado_erp(erp_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol != 'admin':
            cur.execute(
                "SELECT ultimo_envio, ultimo_estado FROM integraciones_erp WHERE id::text = %s AND empresa_id = %s",
                (str(erp_id), request.empresa_id)
            )
        else:
            cur.execute(
                "SELECT ultimo_envio, ultimo_estado FROM integraciones_erp WHERE id::text = %s",
                (str(erp_id),)
            )
        row = cur.fetchone()
        return jsonify({
            'ultimoEnvio': str(row[0]) if row and row[0] else None,
            'ultimoEstado': row[1] if row and row[1] else ''
        })
    finally:
        cur.close()
        conn.close()


@erp_bp.route('/api/dispositivos/erp-config', methods=['GET'])
@token_opcional
def erp_config_dispositivo():
    empresa_id = request.empresa_id
    if not empresa_id:
        return jsonify([])

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT id, nombre, tipo, webhook_url, headers, field_map, envio_auto, activo
               FROM integraciones_erp
               WHERE empresa_id = %s AND activo = TRUE AND envio_auto = TRUE""",
            (empresa_id,)
        )
        rows = cur.fetchall()
        return jsonify([{
            'id': str(r[0]),
            'nombre': r[1],
            'tipo': r[2],
            'webhookUrl': r[3],
            'headers': r[4] or '{}',
            'fieldMap': r[5] or '{}',
            'envioAuto': r[6],
            'activo': r[7],
        } for r in rows])
    finally:
        cur.close()
        conn.close()
