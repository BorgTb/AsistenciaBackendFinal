from flask import Blueprint, request, jsonify
from database import get_connection

personas_bp = Blueprint('personas', __name__)


def _email_valido(email):
    if email is None:
        return True
    email = str(email).strip()
    return email == '' or '@' in email

@personas_bp.route('/api/personas', methods=['GET'])
def get_personas():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, rut, email, huella_id, created_at FROM personas ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    personas = []
    for r in rows:
        personas.append({
            "id": str(r[0]), # <-- Parseado a string para que el ESP32 no sufra
            "nombre": r[1],
            "rut": r[2],
            "email": r[3] if r[3] else "", # Por si algún email viene nulo desde la BD
            "huella_id": r[4] if r[4] else 0,
            "fecha_registro": str(r[5]), # <-- Homologado con el Arduino
            "sincronizado": True # <-- Flag vital para el almacenamiento local
        })
    return jsonify(personas)


@personas_bp.route('/api/personas', methods=['POST'])
def create_persona():
    data = request.json
    if not data.get('nombre') or not data.get('rut'):
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO personas (nombre, rut, email, huella_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (
            data['nombre'],
            data['rut'],
            data.get('email', ''),
            data.get('huella_id')
        ))
        persona_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'ok': True, 'id': persona_id})
    except Exception as e:
        conn.rollback()
        # --- NUEVO: Imprimir el error real en la consola ---
        print(f"❌ ERROR FATAL POSTGRESQL: {str(e)}")
        # ---------------------------------------------------
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@personas_bp.route('/api/personas/<persona_id>', methods=['PUT', 'PATCH'])
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
        cur.execute('SELECT id FROM personas WHERE id::text = %s', (str(persona_id),))
        if not cur.fetchone():
            return jsonify({'error': 'Persona no encontrada'}), 404

        query = f"""
            UPDATE personas
            SET {', '.join(campos)}
            WHERE id::text = %s
            RETURNING id, nombre, rut, email, huella_id, created_at
        """
        valores.append(str(persona_id))
        cur.execute(query, tuple(valores))
        row = cur.fetchone()
        conn.commit()

        return jsonify({
            'ok': True,
            'persona': {
                'id': str(row[0]),
                'nombre': row[1],
                'rut': row[2],
                'email': row[3] if row[3] else '',
                'huella_id': row[4] if row[4] else 0,
                'fecha_registro': str(row[5]),
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
        cur.execute('SELECT id FROM personas WHERE id::text = %s', (str(persona_id),))
        if not cur.fetchone():
            return jsonify({'error': 'Persona no encontrada'}), 404

        cur.execute(
            'SELECT id FROM personas WHERE huella_id = %s AND id::text <> %s',
            (huella_id, str(persona_id))
        )
        conflicto = cur.fetchone()
        if conflicto:
            return jsonify({'error': 'huella_id ya asignada a otra persona', 'persona_id': str(conflicto[0])}), 409

        cur.execute(
            """
            UPDATE personas
            SET huella_id = %s
            WHERE id::text = %s
            RETURNING id, nombre, rut, email, huella_id, created_at
            """,
            (huella_id, str(persona_id))
        )
        row = cur.fetchone()
        conn.commit()

        return jsonify({
            'ok': True,
            'persona': {
                'id': str(row[0]),
                'nombre': row[1],
                'rut': row[2],
                'email': row[3] if row[3] else '',
                'huella_id': row[4] if row[4] else 0,
                'fecha_registro': str(row[5]),
                'sincronizado': True,
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@personas_bp.route('/api/personas/<persona_id>', methods=['DELETE'])
def delete_persona(persona_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # PostgreSQL arrojará error si esta persona tiene asistencias o asignaciones debido a llaves foráneas.
        # Lo ideal es que tu BD tenga "ON DELETE CASCADE", o borrar primero los hijos.
        cur.execute("DELETE FROM personas WHERE id::text = %s", (str(persona_id),))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()