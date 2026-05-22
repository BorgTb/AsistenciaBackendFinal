import json

import requests
from flask import Blueprint, jsonify, request
from database import get_connection

erp_bp = Blueprint('erp', __name__)


@erp_bp.route('/api/erp', methods=['GET'])
def get_erp():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nombre, tipo, webhook_url, headers, field_map, envio_auto, activo, created_at
        FROM integraciones_erp
        ORDER BY id
    """)
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
            'createdAt': str(r[8]) if r[8] else None,
        }
        for r in rows
    ])


@erp_bp.route('/api/erp', methods=['POST'])
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

    if isinstance(headers, dict):
        headers = json.dumps(headers, ensure_ascii=False)
    if isinstance(field_map, dict):
        field_map = json.dumps(field_map, ensure_ascii=False)

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO integraciones_erp (nombre, tipo, webhook_url, headers, field_map, envio_auto, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (nombre, tipo, webhook_url, str(headers), str(field_map), envio_auto, activo))
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
def delete_erp(erp_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
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
def test_erp(erp_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT nombre, tipo, webhook_url, headers, field_map, envio_auto, activo
        FROM integraciones_erp
        WHERE id::text = %s
    """, (str(erp_id),))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'mensaje': 'Integración no encontrada'}), 404

    nombre, tipo, webhook_url, headers_text, field_map_text, envio_auto, activo = row

    if not activo:
        return jsonify({'ok': False, 'mensaje': 'La integración está inactiva'}), 400

    try:
        headers = json.loads(headers_text or '{}')
    except Exception:
        headers = {}

    payload = {
        'nombre': nombre,
        'tipo': tipo,
        'webhook_url': webhook_url,
        'field_map': field_map_text or '{}',
        'envio_auto': envio_auto,
        'test': True,
    }

    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=8)
        return jsonify({
            'ok': response.ok,
            'status_code': response.status_code,
            'mensaje': 'Test ejecutado',
            'respuesta': response.text[:500]
        })
    except Exception as e:
        return jsonify({'ok': False, 'mensaje': str(e)}), 200