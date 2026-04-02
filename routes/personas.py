from flask import Blueprint, request, jsonify
from database import get_connection

personas_bp = Blueprint('personas', __name__)

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
            "id": r[0],
            "nombre": r[1],
            "rut": r[2],
            "email": r[3],
            "huella_id": r[4],
            "created_at": str(r[5])
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