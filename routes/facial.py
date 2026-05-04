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
import uuid
from datetime import datetime

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

    # 1. Procesar la imagen y sacar el embedding
    file_path = guardar_imagen_de_registro(persona_id, imagen_b64) # Tu función actual
    
    try:
        resultado = DeepFace.represent(
            img_path=file_path,
            model_name="Facenet",
            enforce_detection=True, # Obligatorio para evitar fotos del techo
            detector_backend="retinaface"
        )
        nuevo_embedding = np.array(resultado[0]['embedding'])

        # --- VALIDACIÓN DE DUPLICADOS ---
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, encoding_facial FROM personas WHERE encoding_facial IS NOT NULL")
        registros_existentes = cur.fetchall()

        UMBRAL_DUPLICADO = 10.0 # Si la distancia es menor a 10, es la misma persona

        for ex_id, ex_nombre, ex_encoding in registros_existentes:
            embedding_db = np.array(json.loads(ex_encoding))
            distancia = np.linalg.norm(embedding_db - nuevo_embedding)

            if distancia < UMBRAL_DUPLICADO:
                cur.close()
                conn.close()
                # Borramos la foto física que se acaba de crear porque no la usaremos
                if os.path.exists(file_path):
                    os.unlink(file_path)
                return jsonify({
                    'error': 'Rostro ya registrado',
                    'mensaje': f'Esta persona ya está registrada como "{ex_nombre}" (ID: {ex_id})'
                }), 409 # Código 409: Conflicto
        
        # --- SI PASA LA VALIDACIÓN, GUARDAR ---
        encoding_json = json.dumps(nuevo_embedding.tolist())
        cur.execute(
            "UPDATE personas SET encoding_facial = %s WHERE id = %s",
            (encoding_json, persona_id)
        )
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'ok': True, 'mensaje': 'Registro exitoso'}), 200

    except ValueError:
        if os.path.exists(file_path): os.unlink(file_path)
        return jsonify({'error': 'No se detectó un rostro claro'}), 400
    except Exception as e:
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

        resultado = DeepFace.represent(
            img_path=file_path,
            model_name="Facenet",
            enforce_detection=True,
            detector_backend="retinaface",
            anti_spoofing=True
        )
        embedding = resultado[0]['embedding']

        cur.execute(
            "UPDATE personas SET encoding_facial = %s WHERE id::text = %s",
            (json.dumps(embedding), str(persona_id))
        )
        conn.commit()

        preview_url = f"{request.host_url.rstrip('/')}/static/previews/{file_name}"
        return jsonify({
            'ok': True,
            'mensaje': 'Rostro actualizado correctamente',
            'preview_url': preview_url
        })

    except ValueError:
        return jsonify({'error': 'No se detecto rostro en la imagen'}), 400
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

            
@facial_bp.route('/api/facial/identificar', methods=['POST'])
def identificar_facial():
    data = request.json
    if not data or 'imagen' not in data:
        return jsonify({'error': 'No se proporcionó imagen'}), 400

    imagen_b64 = data['imagen']
    
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
        img_bytes = base64.b64decode(imagen_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img.save(file_path)
        
        print(f"📸 [AUDITORÍA] Foto guardada para revisión en: {file_path}")
        
        # 2. Extraer el mapa facial de la captura recién guardada
        print("🧠 Extrayendo mapa facial...")
        resultado = DeepFace.represent(
            img_path=file_path,
            model_name="Facenet",
            enforce_detection=True, # Vital: no crashea si sale borrosa
            detector_backend="retinaface",
            anti_spoofing=True
        )
        
        embedding_captura = np.array(resultado[0]['embedding'])
        
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
            embedding_db = np.array(json.loads(row[1]))
            distancia = np.linalg.norm(embedding_db - embedding_captura)
            
            if distancia < mejor_distancia:
                mejor_distancia = distancia
                persona_identificada_id = persona_id
                
        # 5. Evaluar si supera el umbral
        UMBRAL_FACENET = 10.0
        
        if mejor_distancia < UMBRAL_FACENET:
            print(f"🟢 ID: {persona_identificada_id} (Distancia: {round(mejor_distancia, 2)})")
            # Opcional: Podrías renombrar la foto aquí si quieres saber de quién fue
            return jsonify({'ok': True, 'persona_id': str(persona_identificada_id)}), 200
        else:
            print(f"🟡 Desconocido. Distancia: {round(mejor_distancia, 2)}")
            return jsonify({'error': 'Rostro no reconocido. Distancia muy alta.'}), 404

    except ValueError:
        print("🔴 DeepFace no encontró ningún rostro en la foto.")
        return jsonify({'error': 'No se detectó ningún rostro humano'}), 400
    except Exception as e:
        print(f"🔴 Error grave: {e}")
        return jsonify({'error': str(e)}), 500
        
    # ELIMINAMOS el bloque 'finally' que borraba la foto. ¡Ahora se quedan guardadas!