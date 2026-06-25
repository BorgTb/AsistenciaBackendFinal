from flask import Blueprint, request, jsonify
from database import get_connection
from routes.auth import token_opcional, requiere_rol
from eventos_mqtt import notificar_sincronizacion
import os


personas_bp = Blueprint('personas', __name__)


PREVIEWS_DIR = os.path.join(os.getcwd(), 'static', 'previews')


def _email_valido(email):
    if email is None:
        return True
    email = str(email).strip()
    return email == '' or '@' in email


@personas_bp.route('/api/personas', methods=['GET'])
@token_opcional
def get_personas():
    conn = get_connection()
    cur = conn.cursor()

    rol = request.user_rol
    empresa_id = request.empresa_id
    persona_id = request.persona_id

    if rol == 'admin':
        cur.execute("SELECT id, nombre, rut, email, huella_id, empresa_id, created_at FROM personas WHERE activo = true ORDER BY id")
    elif rol == 'empleador' and empresa_id:
        cur.execute(
            "SELECT id, nombre, rut, email, huella_id, empresa_id, created_at FROM personas WHERE empresa_id = %s AND activo = true ORDER BY id",
            (empresa_id,)
        )
    elif rol == 'trabajador' and persona_id:
        cur.execute(
            "SELECT id, nombre, rut, email, huella_id, empresa_id, created_at FROM personas WHERE id = %s",
            (persona_id,)
        )
    else:
        if empresa_id:
            cur.execute(
                "SELECT id, nombre, rut, email, huella_id, empresa_id, created_at FROM personas WHERE empresa_id = %s AND activo = true ORDER BY id",
                (empresa_id,)
            )
        elif request.dispositivo_id:
            cur.execute(
                "SELECT empresa_id FROM dispositivos WHERE id = %s AND enrolado = TRUE",
                (request.dispositivo_id,)
            )
            if cur.fetchone():
                cur.execute(
                    "SELECT id, nombre, rut, email, huella_id, empresa_id, created_at FROM personas WHERE dispositivo_origen_id = %s AND activo = true ORDER BY id",
                    (request.dispositivo_id,)
                )
            else:
                cur.execute(
                    "SELECT id, nombre, rut, email, huella_id, empresa_id, created_at FROM personas WHERE dispositivo_origen_id = %s AND empresa_id IS NULL AND activo = true ORDER BY id",
                    (request.dispositivo_id,)
                )
        else:
            cur.close()
            conn.close()
            return jsonify([])

    rows = cur.fetchall()
    cur.close()
    conn.close()

    personas = []
    for r in rows:
        personas.append({
            "id": str(r[0]),
            "nombre": r[1],
            "rut": r[2],
            "email": r[3] if r[3] else "",
            "huella_id": r[4] if r[4] else 0,
            "empresa_id": r[5],
            "fecha_registro": str(r[6]),
            "sincronizado": True
        })
    return jsonify(personas)


@personas_bp.route('/api/personas', methods=['POST'])
@token_opcional
def create_persona():
    data = request.json
    if not data.get('nombre') or not data.get('rut'):
        return jsonify({'error': 'Faltan datos'}), 400

    empresa_id = request.empresa_id

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, nombre, rut FROM personas WHERE rut = %s", (data['rut'],))
        existente = cur.fetchone()
        if existente:
            return jsonify({
                'ok': True,
                'id': existente[0],
                'nombre': existente[1],
                'rut': existente[2],
                'ya_existente': True
            })

        dispositivo_origen_id = request.dispositivo_id if not empresa_id else None

        cur.execute(
            "INSERT INTO personas (empresa_id, dispositivo_origen_id, nombre, rut, email, huella_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (empresa_id, dispositivo_origen_id, data['nombre'], data['rut'], data.get('email', ''), data.get('huella_id'))
        )
        persona_id = cur.fetchone()[0]

        if data.get('consentimiento'):
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            cur.execute(
                "INSERT INTO consentimientos (persona_id, version_politica, ip_dispositivo, metodo_aceptacion) VALUES (%s, '1.0', %s, 'registro') ON CONFLICT (persona_id) DO NOTHING",
                (persona_id, ip)
            )

        conn.commit()
        if empresa_id:
            notificar_sincronizacion(empresa_id, 'personas', 'crear', persona_id)
        return jsonify({'ok': True, 'id': persona_id, 'rut': data['rut'], 'ya_existente': False})
    except Exception as e:
        conn.rollback()
        print(f"ERROR FATAL POSTGRESQL: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/duplicados', methods=['GET'])
@token_opcional
def get_duplicados_pendientes():
    conn = get_connection()
    cur = conn.cursor()
    empresa_id = request.empresa_id
    if not empresa_id:
        cur.close()
        conn.close()
        return jsonify({'error': 'No autorizado'}), 401

    try:
        cur.execute("""
            SELECT dp.id, dp.persona_mantener_id, dp.persona_eliminar_id,
                   dp.tipo_deteccion, dp.created_at,
                   pm.nombre AS nombre_mantener, pm.rut AS rut_mantener,
                   pe.nombre AS nombre_eliminar, pe.rut AS rut_eliminar
            FROM duplicados_pendientes dp
            JOIN personas pm ON pm.id = dp.persona_mantener_id
            JOIN personas pe ON pe.id = dp.persona_eliminar_id
            WHERE dp.empresa_id = %s AND dp.resuelto = FALSE
            ORDER BY dp.created_at DESC
        """, (empresa_id,))
        rows = cur.fetchall()
        return jsonify([{
            'id': r[0],
            'persona_mantener_id': str(r[1]),
            'persona_eliminar_id': str(r[2]),
            'tipo_deteccion': r[3],
            'created_at': str(r[4]),
            'nombre_mantener': r[5],
            'rut_mantener': r[6],
            'nombre_eliminar': r[7],
            'rut_eliminar': r[8]
        } for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/merge', methods=['POST'])
@token_opcional
def merge_personas():
    data = request.json or {}
    mantener_id = data.get('mantener_id')
    eliminar_id = data.get('eliminar_id')

    if not mantener_id or not eliminar_id:
        return jsonify({'error': 'Faltan mantener_id y eliminar_id'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM personas WHERE id::text = %s", (str(mantener_id),))
        if not cur.fetchone():
            return jsonify({'error': 'Persona mantener no encontrada'}), 404

        cur.execute("SELECT id FROM personas WHERE id::text = %s", (str(eliminar_id),))
        if not cur.fetchone():
            return jsonify({'error': 'Persona eliminar no encontrada'}), 404

        mantener_id_int = int(mantener_id)
        eliminar_id_int = int(eliminar_id)

        # 1. Transferir encodings faciales
        cur.execute(
            "UPDATE encodings_faciales SET persona_id = %s WHERE persona_id = %s",
            (mantener_id_int, eliminar_id_int)
        )

        # 2. Transferir huella_id si mantener no tiene una
        cur.execute("SELECT huella_id FROM personas WHERE id = %s", (mantener_id_int,))
        mantener_huella = cur.fetchone()[0]
        if not mantener_huella or mantener_huella == 0:
            cur.execute("SELECT huella_id FROM personas WHERE id = %s", (eliminar_id_int,))
            eliminar_huella = cur.fetchone()[0]
            if eliminar_huella and eliminar_huella > 0:
                cur.execute(
                    "UPDATE personas SET huella_id = %s WHERE id = %s",
                    (eliminar_huella, mantener_id_int)
                )

        # 3. Reasignar asistencias
        cur.execute(
            "UPDATE asistencias SET persona_id = %s WHERE persona_id = %s",
            (mantener_id_int, eliminar_id_int)
        )

        # 4. Reasignar asignaciones
        cur.execute(
            "UPDATE asignaciones SET persona_id = %s WHERE persona_id = %s",
            (mantener_id_int, eliminar_id_int)
        )

        # 5. Transferir consentimiento si mantener no tiene
        cur.execute("SELECT id FROM consentimientos WHERE persona_id = %s", (mantener_id_int,))
        if not cur.fetchone():
            cur.execute(
                "UPDATE consentimientos SET persona_id = %s WHERE persona_id = %s",
                (mantener_id_int, eliminar_id_int)
            )

        # 6. Marcar duplicados_pendientes como resueltos
        cur.execute(
            "UPDATE duplicados_pendientes SET resuelto = TRUE WHERE (persona_mantener_id = %s AND persona_eliminar_id = %s) OR (persona_mantener_id = %s AND persona_eliminar_id = %s)",
            (mantener_id_int, eliminar_id_int, eliminar_id_int, mantener_id_int)
        )

        # 7. Eliminar la persona duplicada
        cur.execute("DELETE FROM personas WHERE id = %s", (eliminar_id_int,))

        conn.commit()

        try:
            from routes.facial import _invalidar_cache
            _invalidar_cache()
        except Exception:
            pass

        return jsonify({'ok': True, 'mensaje': f'Personas fusionadas. {mantener_id_int} conservado, {eliminar_id_int} eliminado.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/<persona_id>/biometrico', methods=['GET'])
@token_opcional
def get_persona_biometrico(persona_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.empresa_id and request.user_rol != 'admin':
            cur.execute(
                "SELECT id, huella_id FROM personas WHERE id::text = %s AND empresa_id = %s",
                (str(persona_id), request.empresa_id)
            )
        else:
            cur.execute(
                "SELECT id, huella_id FROM personas WHERE id::text = %s",
                (str(persona_id),)
            )

        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Persona no encontrada'}), 404

        pid, huella_id = row

        cur.execute(
            "SELECT COUNT(*) FROM encodings_faciales WHERE persona_id = %s",
            (pid,)
        )
        total_encodings = cur.fetchone()[0]

        cur.execute("SELECT id FROM consentimientos WHERE persona_id = %s", (pid,))
        tiene_consentimiento = cur.fetchone() is not None

        import os
        preview_path = os.path.join(os.getcwd(), 'static', 'previews', f'{pid}.jpg')
        tiene_preview = os.path.exists(preview_path)

        return jsonify({
            'persona_id': str(pid),
            'huella_id': huella_id if huella_id else 0,
            'total_encodings': total_encodings,
            'tiene_consentimiento': tiene_consentimiento,
            'tiene_preview': tiene_preview
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/<persona_id>', methods=['PUT', 'PATCH'])
@token_opcional
def update_persona(persona_id):
    data = request.json or {}

    if 'rut' in data:
        return jsonify({'error': 'El RUT no es editable'}), 400

    nombre = data.get('nombre')
    email = data.get('email')

    campos = []
    valores = []

    if nombre is not None:
        nombre = str(nombre).strip()
        if not nombre:
            return jsonify({'error': 'El nombre no puede estar vacio'}), 400
        campos.append('nombre = %s')
        valores.append(nombre)

    if email is not None:
        email = str(email).strip()
        if not _email_valido(email):
            return jsonify({'error': 'Email invalido'}), 400
        campos.append('email = %s')
        valores.append(email)

    if not campos:
        return jsonify({'error': 'No hay campos para actualizar'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.empresa_id and request.user_rol != 'admin':
            cur.execute(
                "SELECT id FROM personas WHERE id::text = %s AND empresa_id = %s",
                (str(persona_id), request.empresa_id)
            )
        else:
            cur.execute("SELECT id FROM personas WHERE id::text = %s", (str(persona_id),))

        if not cur.fetchone():
            return jsonify({'error': 'Persona no encontrada'}), 404

        query = f"UPDATE personas SET {', '.join(campos)} WHERE id::text = %s RETURNING id, nombre, rut, email, huella_id, empresa_id, created_at"
        valores.append(str(persona_id))
        cur.execute(query, tuple(valores))
        row = cur.fetchone()
        conn.commit()

        notificar_sincronizacion(request.empresa_id, 'personas', 'actualizar', int(persona_id))

        return jsonify({
            'ok': True,
            'persona': {
                'id': str(row[0]),
                'nombre': row[1],
                'rut': row[2],
                'email': row[3] if row[3] else '',
                'huella_id': row[4] if row[4] else 0,
                'empresa_id': row[5],
                'fecha_registro': str(row[6]),
                'sincronizado': True,
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/<persona_id>/huella', methods=['PUT'])
@token_opcional
def update_huella_persona(persona_id):
    data = request.json or {}
    if 'huella_id' not in data:
        return jsonify({'error': 'Falta huella_id'}), 400

    try:
        huella_id = int(data.get('huella_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'huella_id invalido'}), 400

    if huella_id <= 0 or huella_id > 127:
        return jsonify({'error': 'huella_id fuera de rango (1-127)'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.empresa_id and request.user_rol != 'admin':
            cur.execute(
                "SELECT id FROM personas WHERE id::text = %s AND empresa_id = %s",
                (str(persona_id), request.empresa_id)
            )
        else:
            cur.execute("SELECT id FROM personas WHERE id::text = %s", (str(persona_id),))

        if not cur.fetchone():
            return jsonify({'error': 'Persona no encontrada'}), 404

        cur.execute(
            "SELECT id FROM personas WHERE huella_id = %s AND id::text <> %s",
            (huella_id, str(persona_id))
        )
        conflicto = cur.fetchone()
        if conflicto:
            return jsonify({'error': 'huella_id ya asignada a otra persona', 'persona_id': str(conflicto[0])}), 409

        cur.execute(
            "UPDATE personas SET huella_id = %s WHERE id::text = %s RETURNING id, nombre, rut, email, huella_id, empresa_id, created_at",
            (huella_id, str(persona_id))
        )
        row = cur.fetchone()
        conn.commit()

        notificar_sincronizacion(request.empresa_id, 'personas', 'actualizar', int(persona_id))

        return jsonify({
            'ok': True,
            'persona': {
                'id': str(row[0]),
                'nombre': row[1],
                'rut': row[2],
                'email': row[3] if row[3] else '',
                'huella_id': row[4] if row[4] else 0,
                'empresa_id': row[5],
                'fecha_registro': str(row[6]),
                'sincronizado': True,
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/<persona_id>/consentimiento', methods=['POST'])
@token_opcional
def registrar_consentimiento(persona_id):
    data = request.get_json(silent=True) or {}
    version_politica = data.get('version_politica', '1.0')
    metodo_aceptacion = data.get('metodo_aceptacion', 'web')
    ip_dispositivo = request.headers.get('X-Forwarded-For', request.remote_addr)

    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.empresa_id and request.user_rol != 'admin':
            cur.execute(
                "SELECT id FROM personas WHERE id::text = %s AND empresa_id = %s",
                (str(persona_id), request.empresa_id)
            )
        elif request.user_rol == 'admin':
            cur.execute("SELECT id FROM personas WHERE id::text = %s", (str(persona_id),))
        else:
            return jsonify({'error': 'No autorizado'}), 403

        if not cur.fetchone():
            return jsonify({'error': 'Persona no encontrada'}), 404

        cur.execute(
            "INSERT INTO consentimientos (persona_id, version_politica, ip_dispositivo, metodo_aceptacion) VALUES (%s, %s, %s, %s) ON CONFLICT (persona_id) DO UPDATE SET fecha_aceptacion = NOW(), version_politica = EXCLUDED.version_politica, metodo_aceptacion = EXCLUDED.metodo_aceptacion",
            (persona_id, version_politica, ip_dispositivo, metodo_aceptacion)
        )
        conn.commit()
        return jsonify({'ok': True, 'mensaje': 'Consentimiento biometrico registrado'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/<persona_id>', methods=['DELETE'])
@token_opcional
def delete_persona(persona_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute(
                "SELECT id, nombre FROM personas WHERE id::text = %s",
                (str(persona_id),)
            )
            row = cur.fetchone()
            if not row:
                return jsonify({'error': 'Persona no encontrada'}), 404

            persona_id_real, nombre = row

            usuario_solicitante = getattr(request, 'user_id', 'anonimo')
            cur.execute(
                "INSERT INTO eliminaciones_biometricas (persona_id, usuario_solicitante) VALUES (%s, %s)",
                (persona_id_real, str(usuario_solicitante))
            )

            cur.execute(
                "UPDATE personas SET rut = NULL, email = NULL, huella_id = NULL, activo = false WHERE id = %s",
                (persona_id_real,)
            )

            cur.execute("DELETE FROM encodings_faciales WHERE persona_id = %s", (persona_id_real,))
            cur.execute("DELETE FROM consentimientos WHERE persona_id = %s", (persona_id_real,))

            foto_path = os.path.join(PREVIEWS_DIR, f"{persona_id_real}.jpg")
            if os.path.exists(foto_path):
                os.unlink(foto_path)

            try:
                from routes.facial import _invalidar_cache
                _invalidar_cache()
            except Exception:
                pass

        elif request.empresa_id:
            cur.execute(
                "UPDATE personas SET activo = false WHERE id::text = %s AND empresa_id = %s",
                (str(persona_id), request.empresa_id)
            )
            if cur.rowcount == 0:
                return jsonify({'error': 'Persona no encontrada'}), 404
        else:
            return jsonify({'error': 'No autorizado'}), 403

        conn.commit()
        notificar_sincronizacion(request.empresa_id, 'personas', 'eliminar', int(persona_id))
        return jsonify({'ok': True, 'mensaje': f'Datos de {nombre} eliminados. Registros de asistencia conservados.' if request.user_rol == 'admin' else 'Persona desactivada.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/<persona_id>/datos-biometricos', methods=['DELETE'])
@token_opcional
def eliminar_datos_biometricos(persona_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.empresa_id and request.user_rol != 'admin':
            cur.execute(
                "SELECT id, nombre FROM personas WHERE id::text = %s AND empresa_id = %s",
                (str(persona_id), request.empresa_id)
            )
        elif request.user_rol == 'admin':
            cur.execute(
                "SELECT id, nombre FROM personas WHERE id::text = %s",
                (str(persona_id),)
            )
        else:
            return jsonify({'error': 'No autorizado'}), 403

        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Persona no encontrada'}), 404

        persona_id_real, nombre = row

        cur.execute(
            "SELECT encoding, foto_path FROM encodings_faciales WHERE persona_id = %s LIMIT 1",
            (persona_id_real,)
        )
        ef_row = cur.fetchone()
        embedding_anterior = ef_row[0] if ef_row else None
        foto_path = ef_row[1] if ef_row else f"static/previews/{persona_id_real}.jpg"

        usuario_solicitante = getattr(request, 'user_id', 'anonimo')

        cur.execute(
            "INSERT INTO eliminaciones_biometricas (persona_id, embedding_anterior, foto_path, usuario_solicitante) VALUES (%s, %s, %s, %s)",
            (persona_id_real, embedding_anterior, foto_path, str(usuario_solicitante))
        )

        cur.execute("UPDATE personas SET huella_id = NULL, rut = NULL, email = NULL WHERE id = %s", (persona_id_real,))

        foto_path = os.path.join(PREVIEWS_DIR, f"{persona_id_real}.jpg")
        if os.path.exists(foto_path):
            os.unlink(foto_path)

        cur.execute("DELETE FROM consentimientos WHERE persona_id = %s", (persona_id_real,))

        cur.execute("DELETE FROM encodings_faciales WHERE persona_id = %s", (persona_id_real,))

        conn.commit()

        notificar_sincronizacion(request.empresa_id, 'personas', 'actualizar', int(persona_id))

        try:
            from routes.facial import _invalidar_cache
            _invalidar_cache()
        except Exception:
            pass

        return jsonify({'ok': True, 'mensaje': f'Datos biometricos de {nombre} eliminados. Registros de asistencia conservados.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
