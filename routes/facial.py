from flask import Blueprint, request, jsonify
from database import get_connection
from deepface import DeepFace
import numpy as np
import base64
import json
from PIL import Image
import io
import tempfile
import os

facial_bp = Blueprint('facial', __name__)

def decodificar_y_guardar(imagen_b64):
    img_bytes = base64.b64decode(imagen_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    img.save(tmp.name)
    tmp.close()
    return tmp.name


@facial_bp.route('/api/facial/registrar', methods=['POST'])
def registrar_facial():
    data = request.json
    persona_id = data.get('persona_id')
    imagen_b64 = data.get('imagen')

    if not persona_id or not imagen_b64:
        return jsonify({'error': 'Faltan datos'}), 400

    tmp_path = None
    try:
        tmp_path = decodificar_y_guardar(imagen_b64)

        resultado = DeepFace.represent(
            img_path=tmp_path,
            model_name="Facenet",
            enforce_detection=True
        )

        embedding = resultado[0]['embedding']

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE personas SET encoding_facial = %s WHERE id = %s",
            (json.dumps(embedding), persona_id)
        )
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'ok': True, 'mensaje': 'Rostro registrado correctamente'})

    except ValueError as e:
        return jsonify({'error': 'No se detecto rostro en la imagen'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@facial_bp.route('/api/facial/verificar', methods=['POST'])
def verificar_facial():
    data = request.json
    persona_id = data.get('persona_id')
    imagen_b64 = data.get('imagen')

    if not persona_id or not imagen_b64:
        return jsonify({'error': 'Faltan datos'}), 400

    tmp_path = None
    try:
        tmp_path = decodificar_y_guardar(imagen_b64)

        # Obtener embedding guardado
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT encoding_facial FROM personas WHERE id = %s",
            (persona_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row or not row[0]:
            return jsonify({'error': 'Persona sin rostro registrado'}), 404

        embedding_db = np.array(json.loads(row[0]))

        # Obtener embedding de la imagen capturada
        resultado = DeepFace.represent(
            img_path=tmp_path,
            model_name="Facenet",
            enforce_detection=True
        )
        embedding_captura = np.array(resultado[0]['embedding'])

        # Distancia euclidiana — Facenet umbral recomendado es 10
        distancia = np.linalg.norm(embedding_db - embedding_captura)

        if distancia < 10:
            confianza = round(max(0, (1 - distancia / 20)) * 100, 1)
            return jsonify({
                'ok': True,
                'confianza': confianza,
                'distancia': round(float(distancia), 3)
            })

        return jsonify({
            'error': 'Rostro no coincide',
            'distancia': round(float(distancia), 3)
        }), 404

    except ValueError:
        return jsonify({'error': 'No se detecto rostro en la imagen'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)