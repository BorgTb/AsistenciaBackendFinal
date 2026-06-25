from flask import Blueprint, request, jsonify
from database import get_connection, resolver_rut_a_id
from routes.auth import token_opcional
from services.email_service import enviar_notificacion_marcacion
import os
import threading

asistencias_bp = Blueprint('asistencias', __name__)


def _erp_push_async(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id):
    if os.getenv('DISABLE_ASYNC_DISPATCH') == '1':
        return
    try:
        from routes.erp import enviar_asistencia_a_erps
        enviar_asistencia_a_erps(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id)
    except Exception:
        pass


def _disparar_erp_push(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id):
    if not empresa_id:
        return
    t = threading.Thread(target=_erp_push_async, args=(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id))
    t.daemon = True
    t.start()


def _email_async(persona_email, nombre, tipo, fecha_hora):
    if os.getenv('DISABLE_ASYNC_DISPATCH') == '1':
        return
    try:
        enviar_notificacion_marcacion(persona_email, nombre, tipo, fecha_hora)
    except Exception:
        pass


def _disparar_email_notificacion(persona_email, nombre, tipo, fecha_hora):
    if not persona_email:
        return
    t = threading.Thread(target=_email_async, args=(persona_email, nombre, tipo, fecha_hora))
    t.daemon = True
    t.start()


@asistencias_bp.route('/api/asistencias', methods=['GET'])
@token_opcional
def get_asistencias():
    conn = get_connection()
    cur = conn.cursor()

    rol = request.user_rol
    empresa_id = request.empresa_id
    persona_id = request.persona_id

    if rol == 'admin':
        cur.execute("""
            SELECT a.id, a.persona_id, p.rut, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.origen, a.sincronizado, a.dispositivo_id
            FROM asistencias a
            JOIN personas p ON a.persona_id = p.id
            ORDER BY a.fecha_hora DESC
            LIMIT 500
        """)
    elif rol == 'empleador' and empresa_id:
        cur.execute("""
            SELECT a.id, a.persona_id, p.rut, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.origen, a.sincronizado, a.dispositivo_id
            FROM asistencias a
            JOIN personas p ON a.persona_id = p.id
            WHERE p.empresa_id = %s
            ORDER BY a.fecha_hora DESC
            LIMIT 500
        """, (empresa_id,))
    elif rol == 'trabajador' and persona_id:
        cur.execute("""
            SELECT a.id, a.persona_id, p.rut, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.origen, a.sincronizado, a.dispositivo_id
            FROM asistencias a
            JOIN personas p ON a.persona_id = p.id
            WHERE a.persona_id = %s
            ORDER BY a.fecha_hora DESC
            LIMIT 200
        """, (persona_id,))
    else:
        cur.execute("""
            SELECT a.id, a.persona_id, p.rut, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.origen, a.sincronizado, a.dispositivo_id
            FROM asistencias a
            JOIN personas p ON a.persona_id = p.id
            ORDER BY a.fecha_hora DESC
            LIMIT 500
        """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([{
        "id": r[0],
        "persona_id": r[1],
        "rut": r[2],
        "nombre": r[3],
        "tipo": r[4],
        "metodo": r[5],
        "fecha_hora": str(r[6]),
        "origen": r[7],
        "sincronizado": r[8],
        "dispositivo_id": r[9]
    } for r in rows])


@asistencias_bp.route('/api/asistencias', methods=['POST'])
def create_asistencia():
    data = request.json or {}
    conn = get_connection()
    cur = conn.cursor()
    try:
        dispositivo_id = data.get('dispositivo_id')
        if not dispositivo_id:
            mac = request.headers.get('X-Device-MAC', '').replace(':', '')
            if mac:
                cur.execute("SELECT id FROM dispositivos WHERE REPLACE(mac_address, ':', '') = %s", (mac,))
                row = cur.fetchone()
                if row:
                    dispositivo_id = row[0]
        nombre = data.get('nombre')
        tipo = data.get('tipo')
        metodo = data.get('metodo', 'huella')

        persona_id = data.get('persona_id')
        if not persona_id and data.get('rut'):
            persona_id = resolver_rut_a_id(data.get('rut'))
            if not persona_id:
                return jsonify({'error': f"Persona con rut {data.get('rut')} no encontrada"}), 404

        turno_id = data.get('turno_id')

        # Deteccion de duplicado: misma persona + mismo turno + mismo tipo + mismo dia
        if persona_id:
            cur.execute(
                "SELECT id, fecha_hora FROM asistencias WHERE persona_id = %s AND tipo = %s AND DATE(fecha_hora) = CURRENT_DATE AND (turno_id = %s OR (turno_id IS NULL AND %s IS NULL))",
                (persona_id, tipo, turno_id, turno_id)
            )
            existente = cur.fetchone()
            if existente:
                return jsonify({'ok': True, 'id': existente[0], 'duplicado': True})

        cur.execute(
            "INSERT INTO asistencias (persona_id, dispositivo_id, nombre, tipo, metodo, origen, sincronizado, turno_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, fecha_hora",
            (persona_id, dispositivo_id, nombre, tipo, metodo, data.get('origen', 'dispositivo'), data.get('sincronizado', False), turno_id)
        )
        row = cur.fetchone()
        asist_id = row[0]
        fecha_hora = row[1]
        conn.commit()

        empresa_id = None
        persona_email = None
        if persona_id:
            cur.execute("SELECT empresa_id, email FROM personas WHERE id = %s", (persona_id,))
            emp_row = cur.fetchone()
            if emp_row:
                empresa_id = emp_row[0]
                persona_email = emp_row[1]

        _disparar_erp_push(persona_id, nombre, tipo, metodo, fecha_hora, empresa_id)
        _disparar_email_notificacion(persona_email, nombre, tipo, fecha_hora)

        # Notificar a otros dispositivos via MQTT
        try:
            from eventos_mqtt import notificar_sincronizacion
            notificar_sincronizacion(empresa_id, 'asistencias', 'crear', asist_id)
        except Exception:
            pass

        return jsonify({'ok': True, 'id': asist_id, 'rut': data.get('rut')})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@asistencias_bp.route('/api/asistencias/sync', methods=['POST'])
def sync_asistencias():
    data = request.json or {}
    registros = data.get('registros', [])
    conn = get_connection()
    cur = conn.cursor()

    # Resolver dispositivo por MAC header
    dispositivo_sync = None
    mac_sync = request.headers.get('X-Device-MAC', '').replace(':', '')
    if mac_sync:
        cur.execute("SELECT id FROM dispositivos WHERE REPLACE(mac_address, ':', '') = %s", (mac_sync,))
        dev_sync = cur.fetchone()
        if dev_sync:
            dispositivo_sync = dev_sync[0]

    insertados = 0
    errores = 0

    for r in registros:
        try:
            persona_id_buscar = r.get('persona_id')
            if not persona_id_buscar and r.get('rut'):
                persona_id_buscar = resolver_rut_a_id(r.get('rut'))
            if not persona_id_buscar:
                errores += 1
                continue

            tipo_buscar = r.get('tipo')
            turno_id_buscar = r.get('turno_id')

            # Deteccion de duplicado
            if persona_id_buscar:
                cur.execute(
                    "SELECT id FROM asistencias WHERE persona_id = %s AND tipo = %s AND DATE(fecha_hora) = CURRENT_DATE AND (turno_id = %s OR (turno_id IS NULL AND %s IS NULL))",
                    (persona_id_buscar, tipo_buscar, turno_id_buscar, turno_id_buscar)
                )
                if cur.fetchone():
                    insertados += 1  # Contar como ok (idempotente)
                    continue

            cur.execute(
                "INSERT INTO asistencias (persona_id, dispositivo_id, nombre, tipo, metodo, origen, sincronizado, turno_id) VALUES (%s, %s, %s, %s, %s, 'sync', TRUE, %s) RETURNING id, fecha_hora",
                (persona_id_buscar, dispositivo_sync, r.get('nombre'), tipo_buscar, r.get('metodo', 'huella'), turno_id_buscar)
            )
            row = cur.fetchone()
            conn.commit()
            insertados += 1

            empresa_id = None
            persona_email = None
            cur.execute("SELECT empresa_id, email FROM personas WHERE id = %s", (persona_id_buscar,))
            emp_row = cur.fetchone()
            if emp_row:
                empresa_id = emp_row[0]
                persona_email = emp_row[1]

            _disparar_erp_push(
                persona_id_buscar, r.get('nombre'), tipo_buscar,
                r.get('metodo', 'huella'), row[1], empresa_id
            )
            _disparar_email_notificacion(persona_email, r.get('nombre'), tipo_buscar, row[1])
        except Exception:
            conn.rollback()
            errores += 1

    try:
        # Resolver dispositivo desde header MAC o desde el payload
        dispositivo_id = data.get('dispositivo_id')
        if not dispositivo_id and registros:
            dispositivo_id = registros[0].get('dispositivo_id')
        mac_header = request.headers.get('X-Device-MAC', '').replace(':', '')
        if mac_header:
            cur.execute("SELECT id, empresa_id FROM dispositivos WHERE REPLACE(mac_address, ':', '') = %s", (mac_header,))
            dev_row = cur.fetchone()
            if dev_row:
                dispositivo_id = str(dev_row[0])
                empresa_notif = dev_row[1]
            else:
                empresa_notif = None
        else:
            empresa_notif = None
            if dispositivo_id is not None:
                cur.execute("SELECT empresa_id FROM dispositivos WHERE id::text = %s", (str(dispositivo_id),))
                row = cur.fetchone()
                empresa_notif = row[0] if row else None

        # Notificar a otros dispositivos via MQTT
        if insertados > 0 and empresa_notif:
            try:
                from eventos_mqtt import notificar_sincronizacion
                notificar_sincronizacion(empresa_notif, 'asistencias', 'batch')
            except Exception:
                pass

        estado = 'ok' if errores == 0 else 'error'
        cur.execute(
            "INSERT INTO sincronizacion_log (dispositivo_id, registros_enviados, registros_ok, estado, detalle) VALUES (%s, %s, %s, %s, %s)",
            (dispositivo_id, len(registros), insertados, estado, f'{errores} errores')
        )
        conn.commit()
        return jsonify({'ok': True, 'insertados': insertados, 'errores': errores})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@asistencias_bp.route('/api/asistencias/device-sync', methods=['GET'])
def device_sync_asistencias():
    mac = request.headers.get('X-Device-MAC', '').replace(':', '')
    if not mac:
        return jsonify({'error': 'X-Device-MAC requerido'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT empresa_id FROM dispositivos WHERE REPLACE(mac_address, ':', '') = %s", (mac,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        empresa_id = row[0]

        cur.execute("""
            SELECT a.id, a.persona_id, p.rut, a.nombre, a.tipo, a.metodo,
                   a.fecha_hora, a.turno_id
            FROM asistencias a
            JOIN personas p ON a.persona_id = p.id
            WHERE p.empresa_id = %s
              AND a.fecha_hora >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY a.fecha_hora ASC
        """, (empresa_id,))
        rows = cur.fetchall()

        return jsonify([{
            "id": r[0],
            "persona_id": str(r[1]),
            "rut": r[2],
            "nombre": r[3],
            "tipo": r[4],
            "metodo": r[5],
            "fecha_hora": str(r[6]),
            "turno_id": str(r[7]) if r[7] is not None else None
        } for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
