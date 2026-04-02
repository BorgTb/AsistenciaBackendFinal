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

# Aseguramos que exista la carpeta estática para las vistas previas
PREVIEWS_DIR = os.path.join(os.getcwd(), 'static', 'previews')
os.makedirs(PREVIEWS_DIR, exist_ok=True)

def decodificar_y_guardar_temporal(imagen_b64):
    """Usado solo para verificaciones rápidas, se borra al terminar"""
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

    # Definimos la ruta permanente donde se guardará la foto de esta persona
    file_name = f"{persona_id}.jpg"
    file_path = os.path.join(PREVIEWS_DIR, file_name)

    try:
        # 1. Decodificar y guardar la imagen permanentemente en la carpeta public (static)
        img_bytes = base64.b64decode(imagen_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img.save(file_path)

        # 2. Analizar el rostro usando la imagen recién guardada
        resultado = DeepFace.represent(
            img_path=file_path,
            model_name="Facenet",
            enforce_detection=True,
            detector_backend="retinaface",
            anti_spoofing=True
        )

        embedding = resultado[0]['embedding']

        # 3. Guardar el mapa facial en la base de datos
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE personas SET encoding_facial = %s WHERE id = %s",
            (json.dumps(embedding), persona_id)
        )
        conn.commit()
        cur.close()
        conn.close()

        # 4. Construir la URL pública para que el ESP32 y el navegador la vean
        # request.host_url te da "http://172.20.10.3:5000/" automáticamente
        preview_url = f"{request.host_url.rstrip('/')}/static/previews/{file_name}"

        return jsonify({
            'ok': True, 
            'mensaje': 'Rostro registrado correctamente',
            'preview_url': preview_url # <--- El ESP32 está esperando este dato exacto
        })

    except ValueError as e:
        # Si DeepFace no detecta un rostro humano válido, borramos la foto mala
        # Agregamos un print para verlo en la consola de tu PC
        print(f"❌ FALLO DE ROSTRO: La imagen se guardó en {file_path} para que la revises.")
        
        return jsonify({'error': 'No se detecto rostro en la imagen'}), 400
        
    except Exception as e:
        if os.path.exists(file_path):
            os.unlink(file_path)
        return jsonify({'error': str(e)}), 500


@facial_bp.route('/api/facial/verificar', methods=['POST'])
def verificar_facial():
    data = request.json
    persona_id = data.get('persona_id')
    imagen_b64 = data.get('imagen')

    if not persona_id or not imagen_b64:
        return jsonify({'error': 'Faltan datos'}), 400

    tmp_path = None
    try:
        tmp_path = decodificar_y_guardar_temporal(imagen_b64)

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

        # Obtener embedding de la imagen capturada temporal
        resultado = DeepFace.represent(
            img_path=tmp_path,
            model_name="Facenet",
            enforce_detection=True,
            detector_backend="retinaface",
            anti_spoofing=True
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
        # Siempre borramos la foto temporal de verificación para no llenar el disco duro
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)