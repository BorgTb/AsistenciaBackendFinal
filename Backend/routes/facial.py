from flask import Blueprint, request, jsonify
from database import get_connection
from deepface import DeepFace
from encryption import cifrar_embedding, descifrar_embedding
import numpy as np
import base64
import json
from PIL import Image
import io
import tempfile
import os
import uuid
import shutil
from datetime import datetime

facial_bp = Blueprint('facial', __name__)

# Aseguramos que exista la carpeta estática para las vistas previas
PREVIEWS_DIR = os.path.join(os.getcwd(), 'static', 'previews')
os.makedirs(PREVIEWS_DIR, exist_ok=True)


def _ip_cliente():
    return request.headers.get('X-Forwarded-For', request.remote_addr)


def _log_biometrico(persona_id, dispositivo_id, tipo_operacion, resultado):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO logs_biometricos (persona_id, dispositivo_id, tipo_operacion, resultado, ip_origen) VALUES (%s, %s, %s, %s, %s)",
            (persona_id, dispositivo_id, tipo_operacion, resultado, _ip_cliente())
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def _verificar_consentimiento(persona_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM consentimientos WHERE persona_id = %s", (persona_id,))
    existe = cur.fetchone()
    cur.close()
    conn.close()
    return existe is not None

def decodificar_y_guardar_temporal(imagen_b64):
    """Usado solo para verificaciones rápidas, se borra al terminar"""
    img_bytes = base64.b64decode(imagen_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    img.save(tmp.name)
    tmp.close()
    return tmp.name


def guardar_imagen_de_registro(persona_id, imagen_b64):
    file_name = f"{persona_id}.jpg"
    file_path = os.path.join(PREVIEWS_DIR, file_name)
    img_bytes = base64.b64decode(imagen_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    img.save(file_path)
    return file_path


def guardar_imagen_temporal(imagen_b64):
    img_bytes = base64.b64decode(imagen_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    img.save(tmp.name)
    tmp.close()
    return tmp.name


def extraer_embedding(img_path, anti_spoofing=False):
    resultado = DeepFace.represent(
        img_path=img_path,
        model_name="Facenet",
        enforce_detection=True,
        detector_backend="retinaface",
        anti_spoofing=anti_spoofing
    )
    return resultado[0]['embedding']


@facial_bp.route('/api/facial/registrar', methods=['POST'])
def registrar_facial():
    data = request.json
    persona_id = data.get('persona_id')
    imagen_b64 = data.get('imagen')

    if not _verificar_consentimiento(persona_id):
        return jsonify({'error': 'Consentimiento biometrico requerido. Acepte la politica de privacidad antes de registrar datos biometricos.'}), 403

    # 1. Procesar la imagen y sacar el embedding
    file_path = guardar_imagen_de_registro(persona_id, imagen_b64) # Tu función actual
    
    try:
        nuevo_embedding = np.array(extraer_embedding(file_path))

        # --- VALIDACIÓN DE DUPLICADOS ---
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, encoding_facial FROM personas WHERE encoding_facial IS NOT NULL")
        registros_existentes = cur.fetchall()

        UMBRAL_DUPLICADO = 10.0 # Si la distancia es menor a 10, es la misma persona

        for ex_id, ex_nombre, ex_encoding in registros_existentes:
            embedding_db = np.array(descifrar_embedding(ex_encoding))
            distancia = np.linalg.norm(embedding_db - nuevo_embedding)

            if distancia < UMBRAL_DUPLICADO:
                cur.close()
                conn.close()
                if os.path.exists(file_path):
                    os.unlink(file_path)
                _log_biometrico(persona_id, None, 'registro', 'duplicado')
                return jsonify({
                    'error': 'Rostro ya registrado',
                    'mensaje': f'Esta persona ya está registrada como "{ex_nombre}" (ID: {ex_id})'
                }), 409 # Código 409: Conflicto
        
        # --- SI PASA LA VALIDACIÓN, GUARDAR ---
        encoding_json = cifrar_embedding(nuevo_embedding.tolist())
        cur.execute(
            "UPDATE personas SET encoding_facial = %s WHERE id = %s",
            (encoding_json, persona_id)
        )
        conn.commit()
        cur.close()
        conn.close()

        _log_biometrico(persona_id, None, 'registro', 'exito')
        return jsonify({'ok': True, 'mensaje': 'Registro exitoso'}), 200

    except ValueError as ve:
        if os.path.exists(file_path): os.unlink(file_path)
        _log_biometrico(persona_id, None, 'registro', 'fallo')
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        _log_biometrico(persona_id, None, 'registro', 'fallo')
        return jsonify({'error': str(e)}), 500

@facial_bp.route('/api/facial/actualizar/<persona_id>', methods=['PUT'])
def actualizar_facial(persona_id):
    data = request.json or {}
    imagen_b64 = data.get('imagen')

    if not imagen_b64:
        return jsonify({'error': 'Falta imagen'}), 400

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM personas WHERE id::text = %s", (str(persona_id),))
        if not cur.fetchone():
            return jsonify({'error': 'Persona no encontrada'}), 404

        file_name = f"{persona_id}.jpg"
        file_path = os.path.join(PREVIEWS_DIR, file_name)

        img_bytes = base64.b64decode(imagen_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img.save(file_path)

        embedding = extraer_embedding(file_path, anti_spoofing=True)

        cur.execute(
            "UPDATE personas SET encoding_facial = %s WHERE id::text = %s",
            (cifrar_embedding(embedding), str(persona_id))
        )
        conn.commit()

        preview_url = f"{request.host_url.rstrip('/')}/static/previews/{file_name}"
        _log_biometrico(persona_id, None, 'registro', 'exito')
        return jsonify({
            'ok': True,
            'mensaje': 'Rostro actualizado correctamente',
            'preview_url': preview_url
        })

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@facial_bp.route('/api/facial/verificar', methods=['POST'])
def verificar_facial():
    data = request.json
    persona_id = data.get('persona_id')
    imagen_b64 = data.get('imagen')

    imagen_b64 += "=" * ((4 - len(imagen_b64) % 4) % 4)

    if not persona_id or not imagen_b64:
        return jsonify({'error': 'Faltan datos'}), 400

    tmp_path = None
    try:
        tmp_path = decodificar_y_guardar_temporal(imagen_b64)
        file_path = guardar_imagen_temporal(imagen_b64)
        import shutil
        copia_debug = f"./static/capturas_prueba/debug_live_{datetime.now().strftime('%H%M%S')}.jpg"
        shutil.copyfile(file_path, copia_debug)
        print(f"📸 Imagen en vivo interceptada y guardada en: {copia_debug}")

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
            _log_biometrico(persona_id, None, 'verificacion', 'no_encontrado')
            return jsonify({'error': 'Persona sin rostro registrado'}), 404

        embedding_db = np.array(descifrar_embedding(row[0]))

        embedding_captura = np.array(extraer_embedding(tmp_path, anti_spoofing=True))

        # Distancia euclidiana — Facenet umbral recomendado es 10
        distancia = np.linalg.norm(embedding_db - embedding_captura)

        if distancia < 10:
            confianza = round(max(0, (1 - distancia / 20)) * 100, 1)
            _log_biometrico(persona_id, None, 'verificacion', 'exito')
            return jsonify({
                'ok': True,
                'confianza': confianza,
                'distancia': round(float(distancia), 3)
            })

        _log_biometrico(persona_id, None, 'verificacion', 'fallo')
        return jsonify({
            'error': 'Rostro no coincide',
            'distancia': round(float(distancia), 3)
        }), 404

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Siempre borramos la foto temporal de verificación para no llenar el disco duro
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

            
@facial_bp.route('/api/facial/identificar', methods=['POST'])
def identificar_facial():
    content_type = (request.content_type or '').lower()
    print(f"📨 [IDENTIFICAR] Content-Type recibido: '{content_type}' | Body size: {len(request.data)} bytes", flush=True)

    # Intentar como octet-stream (JPEG crudo desde ESP32)
    if 'octet-stream' in content_type or (len(request.data) > 0 and 'json' not in content_type):
        img_bytes = request.data
        print(f"📨 [IDENTIFICAR] Interpretado como JPEG crudo ({len(img_bytes)} bytes)", flush=True)
    else:
        # Fallback JSON/Base64 (web, tests)
        try:
            data = request.get_json(force=True, silent=True)
            if data and 'imagen' in data:
                img_bytes = base64.b64decode(data['imagen'])
                print(f"📨 [IDENTIFICAR] Interpretado como JSON/Base64", flush=True)
            else:
                print(f"❌ [IDENTIFICAR] Body no es JSON ni octet-stream", flush=True)
                return jsonify({'error': 'Formato no soportado. Enviar JPEG crudo (octet-stream) o JSON con Base64.'}), 415
        except Exception as e:
            print(f"❌ [IDENTIFICAR] Error decodificando: {e}", flush=True)
            return jsonify({'error': f'Error decodificando: {str(e)}'}), 415
    
    # --- MODO PRUEBA: GUARDAR FOTOS ---
    # Creamos una carpeta especial para no mezclar con las fotos oficiales
    debug_dir = os.path.join(os.getcwd(), 'static', 'capturas_prueba')
    os.makedirs(debug_dir, exist_ok=True)
    
    # Generamos un nombre único con la fecha y hora exacta
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"intento_{timestamp}_{uuid.uuid4().hex[:4]}.jpg"
    file_path = os.path.join(debug_dir, file_name)
    
    try:
        # 1. Decodificar y GUARDAR la imagen físicamente para auditarla
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img.save(file_path)
        
        print(f"📸 [AUDITORÍA] Foto guardada para revisión en: {file_path}")
        
        embedding_captura = np.array(extraer_embedding(file_path, anti_spoofing=True))

        # 3. Traer TODOS los mapas faciales de la Base de Datos
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, encoding_facial FROM personas WHERE encoding_facial IS NOT NULL")
        personas_db = cur.fetchall()
        cur.close()
        conn.close()
        
        if not personas_db:
            return jsonify({'error': 'Base de datos de rostros vacía'}), 404
            
        # 4. Comparar uno a uno
        mejor_distancia = float('inf')
        persona_identificada_id = None
        
        for row in personas_db:
            persona_id = row[0]
            embedding_db = np.array(descifrar_embedding(row[1]))
            distancia = np.linalg.norm(embedding_db - embedding_captura)
            
            if distancia < mejor_distancia:
                mejor_distancia = distancia
                persona_identificada_id = persona_id
                
        # 5. Evaluar si supera el umbral
        UMBRAL_FACENET = 10.0
        
        if mejor_distancia < UMBRAL_FACENET:
            print(f"🟢 ID: {persona_identificada_id} (Distancia: {round(mejor_distancia, 2)})")
            _log_biometrico(persona_identificada_id, None, 'identificacion', 'exito')
            # Opcional: Podrías renombrar la foto aquí si quieres saber de quién fue
            return jsonify({'ok': True, 'persona_id': str(persona_identificada_id)}), 200
        else:
            print(f"🟡 Desconocido. Distancia: {round(mejor_distancia, 2)}")
            _log_biometrico(None, None, 'identificacion', 'fallo')
            return jsonify({'error': 'Rostro no reconocido. Distancia muy alta.'}), 404

    except ValueError as ve:
        print(f"🔴 DeepFace: {ve}")
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        print(f"🔴 Error grave: {e}")
        return jsonify({'error': str(e)}), 500
        
    # ELIMINAMOS el bloque 'finally' que borraba la foto. ¡Ahora se quedan guardadas!