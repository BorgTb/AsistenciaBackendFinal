import os
import datetime
import secrets
import string
from functools import wraps
from flask import Blueprint, request, jsonify
import bcrypt
import jwt

from database import get_connection

auth_bp = Blueprint('auth', __name__)

JWT_SECRET = os.getenv('JWT_SECRET', 'sas-secret-cambiar-en-produccion')
JWT_EXP_HOURS = 24


def token_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return jsonify({'error': 'Token requerido'}), 401

        token = header[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user_id = payload['user_id']
            request.empresa_id = payload['empresa_id']
            request.user_rol = payload['rol']
            request.persona_id = payload.get('persona_id')
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token invalido'}), 401

        return fn(*args, **kwargs)

    return wrapper



def requiere_rol(*roles):
    def decorator(fn):
        @wraps(fn)
        @token_required
        def wrapper(*args, **kwargs):
            if request.user_rol not in roles:
                return jsonify({'error': 'Permisos insuficientes'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def token_opcional(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        request.user_id = None
        request.empresa_id = None
        request.user_rol = None
        request.persona_id = None

        header = request.headers.get('Authorization', '')
        if header.startswith('Bearer '):
            token = header[7:]
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
                request.user_id = payload['user_id']
                request.empresa_id = payload['empresa_id']
                request.user_rol = payload['rol']
                request.persona_id = payload.get('persona_id')
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                pass

        if request.empresa_id is None:
            device_mac = request.headers.get('X-Device-MAC', '').strip()
            if device_mac:
                try:
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT empresa_id FROM dispositivos WHERE REPLACE(mac_address, ':', '') = %s",
                        (device_mac,)
                    )
                    row = cur.fetchone()
                    cur.close()
                    conn.close()
                    if row and row[0] is not None:
                        request.empresa_id = row[0]
                except Exception:
                    pass

        return fn(*args, **kwargs)

    return wrapper



def _puede_crear_rol(rol_creador, rol_a_crear):
    if rol_creador == 'admin':
        return rol_a_crear in ('admin', 'empleador', 'trabajador')
    if rol_creador == 'empleador':
        return rol_a_crear == 'trabajador'
    return False


def _puede_gestionar(rol_gestor, rol_objetivo):
    if rol_gestor == 'admin':
        return True
    if rol_gestor == 'empleador' and rol_objetivo == 'trabajador':
        return True
    return False


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = (data.get('password') or '')
    empresa_id_seleccionada = data.get('empresa_id')

    if not email or not password:
        return jsonify({'error': 'Email y contraseña requeridos'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, nombre, email, password_hash, activo FROM usuarios_web WHERE email = %s",
            (email,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Credenciales invalidas'}), 401

        user_id, nombre, user_email, pw_hash, activo = row

        if not activo:
            return jsonify({'error': 'Usuario desactivado'}), 403

        if not bcrypt.checkpw(password.encode('utf-8'), pw_hash.encode('utf-8')):
            return jsonify({'error': 'Credenciales invalidas'}), 401

        cur.execute(
            """
            SELECT ue.empresa_id, ue.rol, e.nombre as empresa_nombre
            FROM usuario_empresa ue
            JOIN empresas e ON e.id = ue.empresa_id
            WHERE ue.usuario_id = %s AND ue.activo = TRUE
            ORDER BY e.nombre
            """,
            (user_id,)
        )
        empresas = []
        for r in cur.fetchall():
            empresas.append({
                'empresa_id': r[0],
                'rol': r[1],
                'empresa_nombre': r[2]
            })

        if not empresas:
            return jsonify({'error': 'No tienes empresas asignadas. Contacta al administrador.'}), 403

        if len(empresas) == 1:
            elegida = empresas[0]
        elif empresa_id_seleccionada:
            elegida = next((e for e in empresas if str(e['empresa_id']) == str(empresa_id_seleccionada)), None)
            if not elegida:
                return jsonify({'error': 'Empresa no válida para este usuario', 'empresas': empresas}), 403
        else:
            return jsonify({
                'ok': False,
                'need_empresa': True,
                'empresas': empresas,
                'user_name': nombre,
                'user_email': user_email
            })

        empresa_id = elegida['empresa_id']
        rol = elegida['rol']
        empresa_nombre = elegida['empresa_nombre']

        persona_id = None
        if rol == 'trabajador':
            cur.execute(
                "SELECT id FROM personas WHERE empresa_id = %s AND email = %s AND activo = TRUE LIMIT 1",
                (empresa_id, email)
            )
            p_row = cur.fetchone()
            if p_row:
                persona_id = p_row[0]

        payload = {
            'user_id': user_id,
            'empresa_id': empresa_id,
            'rol': rol,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXP_HOURS)
        }
        if persona_id:
            payload['persona_id'] = persona_id

        token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')

        return jsonify({
            'ok': True,
            'token': token,
            'user': {
                'id': user_id,
                'nombre': nombre,
                'email': user_email,
                'rol': rol,
                'empresa_id': empresa_id,
                'empresa_nombre': empresa_nombre,
                'persona_id': persona_id,
                'empresas': empresas
            }
        })
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/register', methods=['POST'])
@requiere_rol('admin', 'empleador')
def register():
    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = (data.get('password') or '')
    rol = (data.get('rol') or 'trabajador').strip().lower()
    empresa_id = data.get('empresa_id', request.empresa_id)

    if not nombre or not email or not password:
        return jsonify({'error': 'Nombre, email y contraseña requeridos'}), 400

    if rol not in ('admin', 'empleador', 'trabajador'):
        return jsonify({'error': 'Rol invalido'}), 400

    if not _puede_crear_rol(request.user_rol, rol):
        return jsonify({'error': 'No tienes permisos para crear ese rol'}), 403

    if request.user_rol == 'admin' and not data.get('empresa_id'):
        return jsonify({'error': 'Debes especificar la empresa'}), 400

    if request.user_rol == 'empleador':
        empresa_id = request.empresa_id

    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM usuarios_web WHERE email = %s", (email,))
        existing = cur.fetchone()
        if existing:
            return jsonify({'error': 'Ya existe un usuario con ese email'}), 409
        else:
            cur.execute(
                "INSERT INTO usuarios_web (nombre, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                (nombre, email, pw_hash)
            )
            user_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO usuario_empresa (usuario_id, empresa_id, rol) VALUES (%s, %s, %s)",
                (user_id, empresa_id, rol)
            )
            conn.commit()
            return jsonify({'ok': True, 'id': user_id, 'mensaje': 'Usuario creado correctamente'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/usuarios', methods=['GET'])
@requiere_rol('admin', 'empleador')
def listar_usuarios():
    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute("""
                SELECT u.id, u.nombre, u.email, ue.rol, u.activo, u.created_at,
                       e.nombre as empresa_nombre, ue.empresa_id
                FROM usuarios_web u
                JOIN usuario_empresa ue ON ue.usuario_id = u.id
                JOIN empresas e ON e.id = ue.empresa_id
                ORDER BY e.nombre, u.id
            """)
        else:
            cur.execute("""
                SELECT u.id, u.nombre, u.email, ue.rol, u.activo, u.created_at,
                       e.nombre as empresa_nombre, ue.empresa_id
                FROM usuarios_web u
                JOIN usuario_empresa ue ON ue.usuario_id = u.id
                JOIN empresas e ON e.id = ue.empresa_id
                WHERE ue.empresa_id = %s AND ue.rol IN ('empleador', 'trabajador')
                ORDER BY u.id
            """, (request.empresa_id,))

        rows = cur.fetchall()
        usuarios = []
        for r in rows:
            usuarios.append({
                'id': r[0],
                'nombre': r[1],
                'email': r[2],
                'rol': r[3],
                'activo': r[4],
                'created_at': str(r[5]) if r[5] else '',
                'empresa_nombre': r[6],
                'empresa_id': r[7]
            })
        return jsonify(usuarios)
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/usuarios/<user_id>', methods=['DELETE'])
@requiere_rol('admin', 'empleador')
def eliminar_usuario(user_id):
    empresa_id = data = request.json or {}
    target_empresa_id = data.get('empresa_id') if request.user_rol == 'admin' else request.empresa_id

    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            cur.execute(
                "SELECT ue.rol FROM usuario_empresa ue WHERE ue.usuario_id = %s AND ue.empresa_id = %s",
                (user_id, target_empresa_id)
            )
        else:
            cur.execute(
                "SELECT ue.rol FROM usuario_empresa ue WHERE ue.usuario_id = %s AND ue.empresa_id = %s",
                (user_id, request.empresa_id)
            )

        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Usuario no encontrado en esta empresa'}), 404

        target_rol = row[0]

        if int(user_id) == request.user_id:
            if request.user_rol == 'admin':
                cur.execute(
                    "DELETE FROM usuario_empresa WHERE usuario_id = %s AND empresa_id = %s",
                    (user_id, target_empresa_id)
                )
                conn.commit()
                return jsonify({'ok': True, 'mensaje': 'Te removiste de esta empresa'})
            return jsonify({'error': 'No puedes eliminarte a ti mismo'}), 400

        if not _puede_gestionar(request.user_rol, target_rol):
            return jsonify({'error': 'No tienes permisos para eliminar este usuario'}), 403

        cur.execute(
            "DELETE FROM usuario_empresa WHERE usuario_id = %s AND empresa_id = %s",
            (user_id, target_empresa_id if request.user_rol == 'admin' else request.empresa_id)
        )
        conn.commit()
        return jsonify({'ok': True, 'mensaje': 'Usuario removido de la empresa'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/usuarios/<user_id>', methods=['PUT'])
@requiere_rol('admin', 'empleador')
def editar_usuario(user_id):
    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = (data.get('password') or '')
    rol = (data.get('rol') or '').strip().lower()
    activo = data.get('activo')

    conn = get_connection()
    cur = conn.cursor()
    try:
        if request.user_rol == 'admin':
            empresa_id = data.get('empresa_id')
            cur.execute(
                "SELECT u.id, u.nombre, u.email, u.activo, ue.rol, ue.empresa_id "
                "FROM usuarios_web u JOIN usuario_empresa ue ON ue.usuario_id = u.id "
                "WHERE u.id = %s AND ue.empresa_id = %s",
                (user_id, empresa_id)
            )
        else:
            cur.execute(
                "SELECT u.id, u.nombre, u.email, u.activo, ue.rol, ue.empresa_id "
                "FROM usuarios_web u JOIN usuario_empresa ue ON ue.usuario_id = u.id "
                "WHERE u.id = %s AND ue.empresa_id = %s",
                (user_id, request.empresa_id)
            )

        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Usuario no encontrado en esta empresa'}), 404

        target_rol = row[4]
        target_empresa_id = row[5]

        if not _puede_gestionar(request.user_rol, target_rol):
            return jsonify({'error': 'No tienes permisos para editar este usuario'}), 403

        es_self_edit = int(user_id) == request.user_id

        updates_web = []
        params_web = []

        if nombre:
            updates_web.append("nombre = %s")
            params_web.append(nombre)
        if email:
            updates_web.append("email = %s")
            params_web.append(email)
        if password:
            nuevo_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            updates_web.append("password_hash = %s")
            params_web.append(nuevo_hash)
        if activo is not None and not es_self_edit:
            updates_web.append("activo = %s")
            params_web.append(bool(activo))

        if updates_web:
            params_web.append(user_id)
            cur.execute(
                f"UPDATE usuarios_web SET {', '.join(updates_web)} WHERE id = %s",
                params_web
            )

        nuevo_rol = rol if rol in ('admin', 'empleador', 'trabajador') and not es_self_edit else None
        if nuevo_rol and request.user_rol == 'empleador':
            nuevo_rol = 'trabajador'

        if nuevo_rol or (request.user_rol == 'admin' and empresa_id is not None and not es_self_edit):
            cur.execute(
                "UPDATE usuario_empresa SET rol = %s WHERE usuario_id = %s AND empresa_id = %s",
                (nuevo_rol or target_rol, user_id, target_empresa_id)
            )

        conn.commit()
        return jsonify({'ok': True, 'mensaje': 'Usuario actualizado correctamente'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/empresas', methods=['GET'])
@requiere_rol('admin')
def listar_empresas():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, nombre, rut_empresa, email_contacto, telefono, direccion, created_at FROM empresas ORDER BY id")
        rows = cur.fetchall()
        empresas = []
        for r in rows:
            empresas.append({
                'id': r[0],
                'nombre': r[1],
                'rut_empresa': r[2],
                'email_contacto': r[3],
                'telefono': r[4],
                'direccion': r[5],
                'created_at': str(r[6]) if r[6] else ''
            })
        return jsonify(empresas)
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/empresas', methods=['POST'])
@requiere_rol('admin')
def crear_empresa():
    data = request.json or {}
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'Nombre requerido'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO empresas (nombre, rut_empresa, email_contacto, telefono, direccion) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (nombre, data.get('rut_empresa', ''), data.get('email_contacto', ''), data.get('telefono', ''), data.get('direccion', ''))
        )
        empresa_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'ok': True, 'id': empresa_id, 'mensaje': 'Empresa creada'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/empresas/<empresa_id>', methods=['DELETE'])
@requiere_rol('admin')
def eliminar_empresa(empresa_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM empresas WHERE id = %s", (empresa_id,))
        conn.commit()
        return jsonify({'ok': True, 'mensaje': 'Empresa eliminada'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/asignar-usuario', methods=['POST'])
@requiere_rol('admin')
def asignar_usuario_empresa():
    data = request.json or {}
    usuario_id = data.get('usuario_id')
    empresa_id = data.get('empresa_id')
    rol = data.get('rol', 'trabajador')

    if not usuario_id or not empresa_id:
        return jsonify({'error': 'usuario_id y empresa_id requeridos'}), 400

    if rol not in ('admin', 'empleador', 'trabajador'):
        return jsonify({'error': 'Rol invalido'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO usuario_empresa (usuario_id, empresa_id, rol)
               VALUES (%s, %s, %s)
               ON CONFLICT (usuario_id, empresa_id) DO UPDATE SET rol = EXCLUDED.rol""",
            (usuario_id, empresa_id, rol)
        )
        conn.commit()
        return jsonify({'ok': True, 'mensaje': 'Usuario asignado a la empresa'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/register-company', methods=['POST'])
def registrar_empresa():
    data = request.json or {}
    empresa_nombre = (data.get('empresa_nombre') or '').strip()
    admin_nombre = (data.get('admin_nombre') or '').strip()
    admin_email = (data.get('admin_email') or '').strip().lower()
    admin_password = (data.get('admin_password') or '')

    if not empresa_nombre or not admin_nombre or not admin_email or not admin_password:
        return jsonify({'error': 'Nombre de empresa, nombre, email y contraseña del administrador requeridos'}), 400

    if len(admin_password) < 4:
        return jsonify({'error': 'La contraseña debe tener al menos 4 caracteres'}), 400

    if '@' not in admin_email:
        return jsonify({'error': 'Email invalido'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM usuarios_web WHERE email = %s", (admin_email,))
        if cur.fetchone():
            return jsonify({'error': 'Ya existe un usuario con ese email'}), 409

        cur.execute(
            "INSERT INTO empresas (nombre) VALUES (%s) RETURNING id",
            (empresa_nombre,)
        )
        empresa_id = cur.fetchone()[0]

        pw_hash = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cur.execute(
            "INSERT INTO usuarios_web (nombre, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (admin_nombre, admin_email, pw_hash)
        )
        user_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO usuario_empresa (usuario_id, empresa_id, rol) VALUES (%s, %s, %s)",
            (user_id, empresa_id, 'admin')
        )

        conn.commit()

        payload = {
            'user_id': user_id,
            'empresa_id': empresa_id,
            'rol': 'admin',
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXP_HOURS)
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')

        return jsonify({
            'ok': True,
            'token': token,
            'user': {
                'id': user_id,
                'nombre': admin_nombre,
                'email': admin_email,
                'rol': 'admin',
                'empresa_id': empresa_id,
                'empresa_nombre': empresa_nombre,
                'persona_id': None,
                'empresas': [{
                    'empresa_id': empresa_id,
                    'rol': 'admin',
                    'empresa_nombre': empresa_nombre
                }]
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/change-password', methods=['PUT'])
@token_required
def cambiar_password():
    data = request.json or {}
    password_actual = data.get('password_actual', '')
    password_nueva = data.get('password_nueva', '')

    if not password_actual or not password_nueva:
        return jsonify({'error': 'Contraseña actual y nueva requeridas'}), 400

    if len(password_nueva) < 4:
        return jsonify({'error': 'La nueva contraseña debe tener al menos 4 caracteres'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT password_hash FROM usuarios_web WHERE id = %s AND activo = TRUE", (request.user_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Usuario no encontrado'}), 404

        if not bcrypt.checkpw(password_actual.encode('utf-8'), row[0].encode('utf-8')):
            return jsonify({'error': 'Contraseña actual incorrecta'}), 401

        nuevo_hash = bcrypt.hashpw(password_nueva.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cur.execute("UPDATE usuarios_web SET password_hash = %s WHERE id = %s", (nuevo_hash, request.user_id))
        conn.commit()
        return jsonify({'ok': True, 'mensaje': 'Contraseña actualizada'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/me', methods=['GET'])
@token_required
def me():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, nombre, email, activo FROM usuarios_web WHERE id = %s",
            (request.user_id,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Usuario no encontrado'}), 404

        cur.execute(
            """
            SELECT ue.empresa_id, ue.rol, e.nombre
            FROM usuario_empresa ue
            JOIN empresas e ON e.id = ue.empresa_id
            WHERE ue.usuario_id = %s AND ue.activo = TRUE
            """,
            (request.user_id,)
        )
        empresas = []
        for r in cur.fetchall():
            empresas.append({'empresa_id': r[0], 'rol': r[1], 'empresa_nombre': r[2]})

        persona_id = None
        if request.user_rol == 'trabajador':
            cur.execute(
                "SELECT id FROM personas WHERE empresa_id = %s AND email = %s AND activo = TRUE LIMIT 1",
                (request.empresa_id, row[2])
            )
            p_row = cur.fetchone()
            if p_row:
                persona_id = p_row[0]

        return jsonify({
            'user': {
                'id': row[0],
                'nombre': row[1],
                'email': row[2],
                'rol': request.user_rol,
                'empresa_id': request.empresa_id,
                'empresa_nombre': next((e['empresa_nombre'] for e in empresas if e['empresa_id'] == request.empresa_id), ''),
                'persona_id': persona_id,
                'empresas': empresas
            }
        })
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/dispositivos/generar-pin', methods=['POST'])
@requiere_rol('admin', 'empleador')
def generar_pin_enrolamiento():
    empresa_id = request.empresa_id
    data = request.json or {}
    nombre = (data.get('nombre') or 'Nuevo dispositivo').strip()
    pin = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, codigo_enrol FROM dispositivos WHERE empresa_id = %s AND enrolado = FALSE AND codigo_enrol IS NOT NULL ORDER BY id DESC LIMIT 1",
            (empresa_id,)
        )
        existing = cur.fetchone()
        if existing:
            device_id = existing[0]
            pin = existing[1]
        else:
            cur.execute(
                "INSERT INTO dispositivos (empresa_id, nombre, codigo_enrol, enrolado) VALUES (%s, %s, %s, FALSE) RETURNING id",
                (empresa_id, nombre, pin)
            )
            device_id = cur.fetchone()[0]
            conn.commit()
        return jsonify({'ok': True, 'pin': pin, 'dispositivo_id': device_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/api/auth/dispositivos/enrolar', methods=['POST'])
def enrolar_dispositivo():
    data = request.json or {}
    codigo = (data.get('codigo') or data.get('pin') or '').strip()
    mac = (data.get('mac') or '').strip()
    ip = (data.get('ip') or data.get('ip_local') or '').strip()

    if not codigo:
        return jsonify({'error': 'PIN requerido'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, empresa_id, enrolado FROM dispositivos WHERE codigo_enrol = %s", (codigo,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'PIN invalido'}), 404

        device_id, empresa_id, enrolado = row

        if enrolado:
            return jsonify({'error': 'Este PIN ya fue usado'}), 409

        cur.execute(
            "UPDATE dispositivos SET mac_address = %s, ip_local = %s, codigo_enrol = NULL, enrolado = TRUE, estado = 'activo' WHERE id = %s",
            (mac, ip, device_id)
        )
        conn.commit()

        return jsonify({'ok': True, 'dispositivo_id': device_id, 'empresa_id': empresa_id, 'mensaje': 'Dispositivo enrolado'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
