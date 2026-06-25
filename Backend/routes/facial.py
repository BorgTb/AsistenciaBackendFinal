from flask import Blueprint, request, jsonify
from database import get_connection, resolver_rut_a_id
from deepface import DeepFace
from encryption import cifrar_embedding, descifrar_embedding
import numpy as np
import cv2
import base64
import json
from PIL import Image
import io
import tempfile
import os
import uuid
import shutil
import time
import threading
from datetime import datetime

facial_bp = Blueprint('facial', __name__)

DETECTOR_BACKEND = os.getenv('FACIAL_DETECTOR', 'mtcnn')
UMBRAL_NITIDEZ = float(os.getenv('FACIAL_NITIDEZ_UMBRAL', '50'))
UMBRAL_DISTANCIA = float(os.getenv('FACIAL_UMBRAL_DISTANCIA', '10.0'))
CACHE_TTL = int(os.getenv('FACIAL_CACHE_TTL', '60'))

_cache_embeddings = {}
_cache_timestamp = 0
_cache_lock = threading.Lock()

def _obtener_embeddings():
    global _cache_embeddings, _cache_timestamp
    now = time.time()
    if now - _cache_timestamp > CACHE_TTL:
        with _cache_lock:
            if now - _cache_timestamp > CACHE_TTL:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("""
                    SELECT ef.persona_id, ef.encoding
                    FROM encodings_faciales ef
                    JOIN personas p ON p.id = ef.persona_id
                    WHERE p.activo = TRUE
                """)
                rows = cur.fetchall()
                cur.close()
                conn.close()

                nuevos = {}
                for pid, enc in rows:
                    try:
                        emb = np.array(descifrar_embedding(enc))
                        nuevos.setdefault(pid, []).append(emb)
                    except Exception:
                        pass

                _cache_embeddings = nuevos
                _cache_timestamp = now

    return _cache_embeddings

def _invalidar_cache():
    global _cache_timestamp
    _cache_timestamp = 0

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

def _resolver_persona_id(data):
    """Resuelve el persona_id desde el payload, aceptando 'persona_id' o 'rut'."""
    persona_id = data.get('persona_id')
    if persona_id:
        return persona_id
    rut = data.get('rut')
    if rut:
        return resolver_rut_a_id(rut)
    return None

def _validar_calidad_imagen(img_path):
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return False, "No se pudo leer la imagen", 0.0
    varianza = cv2.Laplacian(img, cv2.CV_64F).var()
    if varianza < UMBRAL_NITIDEZ:
        return False, f"Imagen con baja nitidez ({varianza:.1f}), posible spoof o captura borrosa", varianza
    return True, "", varianza

def decodificar_y_guardar_temporal(imagen_b64):
    img_bytes = base64.b64decode(imagen_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    img.save(tmp.name)
    tmp.close()
    return tmp.name

def guardar_imagen_de_registro(persona_id, imagen_b64, suffix=''):
    file_name = f"{persona_id}{suffix}.jpg"
    file_path = os.path.join(tempfile.gettempdir(), file_name)
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
        detector_backend=DETECTOR_BACKEND,
        anti_spoofing=anti_spoofing
    )
    return resultado[0]['embedding']

@facial_bp.route('/api/facial/registrar', methods=['POST'])
def registrar_facial():
    data = request.json or {}
    imagen_b64 = data.get('imagen')

    if (not data.get('rut') and not data.get('persona_id')) or not imagen_b64:
        return jsonify({'error': 'Faltan datos (persona_id o rut requerido)'}), 400

    persona_id = _resolver_persona_id(data)
    if not persona_id:
        return jsonify({'error': 'Persona no encontrada'}), 404

    if not _verificar_consentimiento(persona_id):
        return jsonify({'error': 'Consentimiento biometrico requerido. Acepte la politica de privacidad antes de registrar datos biometricos.'}), 403

    try:
        file_path = guardar_imagen_de_registro(persona_id, imagen_b64)
    except Exception as e:
        return jsonify({'error': f'Error al guardar imagen: {str(e)}'}), 500

    try:
        ok_calidad, msg_calidad, quality_score = _validar_calidad_imagen(file_path)
        if not ok_calidad:
            if os.path.exists(file_path):
                os.unlink(file_path)
            _log_biometrico(persona_id, None, 'registro', 'fallo')
            return jsonify({'error': msg_calidad}), 400

        nuevo_embedding = np.array(extraer_embedding(file_path))

        embeddings_dict = _obtener_embeddings()
        persona_id_str = str(persona_id)
        for pid, lista_embs in embeddings_dict.items():
            for emb in lista_embs:
                distancia = np.linalg.norm(nuevo_embedding - emb)
                if distancia < UMBRAL_DISTANCIA and str(pid) != persona_id_str:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                    _log_biometrico(persona_id, None, 'registro', 'duplicado')
                    conn_name = get_connection()
                    cur_name = conn_name.cursor()
                    cur_name.execute("SELECT nombre FROM personas WHERE id = %s", (pid,))
                    row_name = cur_name.fetchone()
                    ex_nombre = row_name[0] if row_name else "Desconocido"
                    cur_name.close()
                    conn_name.close()
                    return jsonify({
                        'error': 'Rostro ya registrado',
                        'mensaje': f'Esta persona ya esta registrada como "{ex_nombre}" (ID: {pid})'
                    }), 409

        conn = get_connection()
        cur = conn.cursor()
        encoding_json = cifrar_embedding(nuevo_embedding.tolist())
        cur.execute(
            "INSERT INTO encodings_faciales (persona_id, encoding, quality_score) VALUES (%s, %s, %s)",
            (persona_id, encoding_json, quality_score)
        )

        conn.commit()
        cur.close()
        conn.close()

        if os.path.exists(file_path):
            os.unlink(file_path)

        _invalidar_cache()
        _log_biometrico(persona_id, None, 'registro', 'exito')
        return jsonify({'ok': True, 'mensaje': 'Registro exitoso'}), 200

    except ValueError as ve:
        if os.path.exists(file_path):
            os.unlink(file_path)
        _log_biometrico(persona_id, None, 'registro', 'fallo')
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        if os.path.exists(file_path):
            os.unlink(file_path)
        _log_biometrico(persona_id, None, 'registro', 'fallo')
        return jsonify({'error': str(e)}), 500

@facial_bp.route('/api/facial/agregar-foto', methods=['POST'])
def agregar_foto():
    data = request.json or {}
    imagen_b64 = data.get('imagen')

    if (not data.get('rut') and not data.get('persona_id')) or not imagen_b64:
        return jsonify({'error': 'Faltan datos (persona_id o rut requerido)'}), 400

    persona_id = _resolver_persona_id(data)
    if not persona_id:
        return jsonify({'error': 'Persona no encontrada'}), 404

    if not _verificar_consentimiento(persona_id):
        return jsonify({'error': 'Consentimiento biometrico requerido'}), 403

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = guardar_imagen_de_registro(persona_id, imagen_b64, suffix=f'_{ts}')

    try:
        ok_calidad, msg_calidad, quality_score = _validar_calidad_imagen(file_path)
        if not ok_calidad:
            if os.path.exists(file_path):
                os.unlink(file_path)
            _log_biometrico(persona_id, None, 'registro', 'fallo')
            return jsonify({'error': msg_calidad}), 400

        nuevo_embedding = np.array(extraer_embedding(file_path))
        encoding_json = cifrar_embedding(nuevo_embedding.tolist())

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO encodings_faciales (persona_id, encoding, quality_score) VALUES (%s, %s, %s) RETURNING id",
            (persona_id, encoding_json, quality_score)
        )
        enc_id = cur.fetchone()[0]

        total = 0
        cur.execute("SELECT COUNT(*) FROM encodings_faciales WHERE persona_id = %s", (persona_id,))
        row = cur.fetchone()
        if row:
            total = row[0]

        conn.commit()
        cur.close()
        conn.close()

        if os.path.exists(file_path):
            os.unlink(file_path)

        _invalidar_cache()
        _log_biometrico(persona_id, None, 'registro', 'exito')
        return jsonify({'ok': True, 'id': enc_id, 'total_fotos': total, 'mensaje': f'Foto agregada. Total: {total} fotos de referencia.'})
    except ValueError as ve:
        if os.path.exists(file_path):
            os.unlink(file_path)
        _log_biometrico(persona_id, None, 'registro', 'fallo')
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        if os.path.exists(file_path):
            os.unlink(file_path)
        _log_biometrico(persona_id, None, 'registro', 'fallo')
        return jsonify({'error': str(e)}), 500

@facial_bp.route('/api/facial/actualizar/<persona_id>', methods=['PUT'])
def actualizar_facial(persona_id):
    data = request.json or {}
    imagen_b64 = data.get('imagen')

    if not imagen_b64:
        return jsonify({'error': 'Falta imagen'}), 400

    rut = data.get('rut')
    if rut:
        pid = resolver_rut_a_id(rut)
        if not pid:
            return jsonify({'error': f'Persona con rut {rut} no encontrada'}), 404
        persona_id = str(pid)

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM personas WHERE id::text = %s", (str(persona_id),))
        if not cur.fetchone():
            return jsonify({'error': 'Persona no encontrada'}), 404

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = f"{persona_id}_{ts}.jpg"
        file_path = os.path.join(tempfile.gettempdir(), file_name)

        img_bytes = base64.b64decode(imagen_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img.save(file_path)

        ok_calidad, msg_calidad, quality_score = _validar_calidad_imagen(file_path)
        if not ok_calidad:
            if os.path.exists(file_path):
                os.unlink(file_path)
            return jsonify({'error': msg_calidad}), 400

        embedding = extraer_embedding(file_path, anti_spoofing=True)
        encoding_cifrado = cifrar_embedding(embedding)

        cur.execute(
            "INSERT INTO encodings_faciales (persona_id, encoding, quality_score) VALUES (%s, %s, %s)",
            (persona_id, encoding_cifrado, quality_score)
        )
        conn.commit()

        if os.path.exists(file_path):
            os.unlink(file_path)

        _invalidar_cache()

        _log_biometrico(persona_id, None, 'registro', 'exito')
        return jsonify({
            'ok': True,
            'mensaje': 'Rostro actualizado correctamente'
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
    data = request.json or {}
    imagen_b64 = data.get('imagen')

    if (not data.get('rut') and not data.get('persona_id')) or not imagen_b64:
        return jsonify({'error': 'Faltan datos (persona_id o rut requerido)'}), 400

    persona_id = _resolver_persona_id(data)
    if not persona_id:
        return jsonify({'error': 'Persona no encontrada'}), 404

    imagen_b64 += "=" * ((4 - len(imagen_b64) % 4) % 4)

    tmp_path = None
    try:
        tmp_path = decodificar_y_guardar_temporal(imagen_b64)

        ok_calidad, msg_calidad, _ = _validar_calidad_imagen(tmp_path)
        if not ok_calidad:
            _log_biometrico(persona_id, None, 'verificacion', 'fallo')
            return jsonify({'error': msg_calidad}), 400

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT encoding FROM encodings_faciales WHERE persona_id = %s",
            (persona_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            _log_biometrico(persona_id, None, 'verificacion', 'no_encontrado')
            return jsonify({'error': 'Persona sin rostro registrado'}), 404

        embedding_captura = np.array(extraer_embedding(tmp_path, anti_spoofing=True))

        mejor_distancia = float('inf')
        for row in rows:
            try:
                embedding_db = np.array(descifrar_embedding(row[0]))
                distancia = np.linalg.norm(embedding_db - embedding_captura)
                if distancia < mejor_distancia:
                    mejor_distancia = distancia
            except Exception:
                pass

        if mejor_distancia < UMBRAL_DISTANCIA:
            confianza = round(max(0, (1 - mejor_distancia / (UMBRAL_DISTANCIA * 2))) * 100, 1)
            _log_biometrico(persona_id, None, 'verificacion', 'exito')
            return jsonify({
                'ok': True,
                'confianza': confianza,
                'distancia': round(float(mejor_distancia), 3)
            })

        _log_biometrico(persona_id, None, 'verificacion', 'fallo')
        return jsonify({
            'error': 'Rostro no coincide',
            'distancia': round(float(mejor_distancia), 3)
        }), 404

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

@facial_bp.route('/api/facial/identificar', methods=['POST'])
def identificar_facial():
    content_type = (request.content_type or '').lower()
    print(f"[IDENTIFICAR] Content-Type recibido: '{content_type}' | Body size: {len(request.data)} bytes", flush=True)

    if 'octet-stream' in content_type:
        img_bytes = request.data
        print(f"[IDENTIFICAR] Interpretado como JPEG crudo ({len(img_bytes)} bytes)", flush=True)
    elif 'json' in content_type:
        data = request.get_json(force=True, silent=True) or {}
        if not data.get('imagen'):
            return jsonify({'error': 'Falta imagen'}), 400
        try:
            img_bytes = base64.b64decode(data['imagen'])
            print(f"[IDENTIFICAR] Interpretado como JSON/Base64", flush=True)
        except Exception as e:
            print(f"[IDENTIFICAR] Error decodificando Base64: {e}", flush=True)
            return jsonify({'error': f'Base64 invalido: {str(e)}'}), 400
    elif not content_type and len(request.data) > 0:
        img_bytes = request.data
        print(f"[IDENTIFICAR] Interpretado como JPEG crudo sin content-type ({len(img_bytes)} bytes)", flush=True)
    else:
        print(f"[IDENTIFICAR] Formato no soportado", flush=True)
        return jsonify({'error': 'Formato no soportado. Enviar JPEG crudo (octet-stream) o JSON con Base64.'}), 415

    if not img_bytes:
        return jsonify({'error': 'Falta imagen'}), 400

    embeddings_dict = _obtener_embeddings()
    if not embeddings_dict:
        return jsonify({'error': 'Base de datos de rostros vacia'}), 404

    debug_dir = os.path.join(os.getcwd(), 'static', 'capturas_prueba')
    os.makedirs(debug_dir, exist_ok=True)

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"intento_{fecha_str}_{uuid.uuid4().hex[:4]}.jpg"
    file_path = os.path.join(debug_dir, file_name)

    try:
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img.save(file_path)

        print(f"[AUDITORIA] Foto guardada en: {file_path}")

        ok_calidad, msg_calidad, _ = _validar_calidad_imagen(file_path)
        if not ok_calidad:
            _log_biometrico(None, None, 'identificacion', 'fallo')
            return jsonify({'error': msg_calidad}), 400

        embedding_captura = np.array(extraer_embedding(file_path, anti_spoofing=True))

        mejor_distancia = float('inf')
        persona_identificada_id = None

        for pid, lista_embs in embeddings_dict.items():
            for emb in lista_embs:
                distancia = np.linalg.norm(embedding_captura - emb)
                if distancia < mejor_distancia:
                    mejor_distancia = distancia
                    persona_identificada_id = pid

        if mejor_distancia < UMBRAL_DISTANCIA:
            rut_encontrado = None
            try:
                conn2 = get_connection()
                cur2 = conn2.cursor()
                cur2.execute("SELECT rut FROM personas WHERE id = %s", (persona_identificada_id,))
                row2 = cur2.fetchone()
                if row2:
                    rut_encontrado = row2[0]
                cur2.close()
                conn2.close()
            except Exception:
                pass
            print(f"ID: {persona_identificada_id} (Distancia: {round(mejor_distancia, 2)})")
            _log_biometrico(persona_identificada_id, None, 'identificacion', 'exito')
            return jsonify({'ok': True, 'persona_id': str(persona_identificada_id), 'rut': rut_encontrado}), 200
        else:
            print(f"Desconocido. Distancia: {round(mejor_distancia, 2)}")
            _log_biometrico(None, None, 'identificacion', 'fallo')
            return jsonify({'error': 'Rostro no reconocido. Distancia muy alta.'}), 404

    except ValueError as ve:
        print(f"DeepFace: {ve}")
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        print(f"Error grave: {e}")
        return jsonify({'error': str(e)}), 500


@facial_bp.route('/api/facial/identificar-o-registrar', methods=['POST'])
def identificar_o_registrar():
    data = request.json or {}
    imagen_b64 = data.get('imagen')
    rut = (data.get('rut') or '').strip()
    consentimiento = data.get('consentimiento', False)

    if not imagen_b64:
        return jsonify({'error': 'Falta imagen'}), 400

    try:
        img_bytes = base64.b64decode(imagen_b64)
    except Exception:
        return jsonify({'error': 'Base64 invalido'}), 400

    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    tmp_path = tmp.name
    img.save(tmp_path)
    tmp.close()

    preview_path = None
    try:
        ok_calidad, msg_calidad, _ = _validar_calidad_imagen(tmp_path)
        if not ok_calidad:
            return jsonify({'error': msg_calidad}), 400

        embedding_captura = np.array(extraer_embedding(tmp_path, anti_spoofing=True))
        embeddings_dict = _obtener_embeddings()

        mejor_distancia = float('inf')
        persona_identificada_id = None
        rut_encontrado = None

        if embeddings_dict:
            for pid, lista_embs in embeddings_dict.items():
                for emb in lista_embs:
                    distancia = np.linalg.norm(embedding_captura - emb)
                    if distancia < mejor_distancia:
                        mejor_distancia = distancia
                        persona_identificada_id = pid

            if mejor_distancia < UMBRAL_DISTANCIA and persona_identificada_id:
                conn2 = get_connection()
                cur2 = conn2.cursor()
                cur2.execute("SELECT rut, nombre FROM personas WHERE id = %s", (persona_identificada_id,))
                row2 = cur2.fetchone()
                cur2.close()
                conn2.close()

                if not row2:
                    _log_biometrico(None, None, 'identificacion', 'fallo')
                    return jsonify({'ok': False, 'error': 'Persona no encontrada en BD'}), 404

                _log_biometrico(persona_identificada_id, None, 'identificacion', 'exito')
                return jsonify({
                    'ok': True,
                    'persona_id': str(persona_identificada_id),
                    'rut': row2[0],
                    'nombre': row2[1]
                })

        if not rut:
            return jsonify({'ok': False, 'error': 'Rostro no reconocido'}), 404

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, nombre FROM personas WHERE rut = %s AND activo = TRUE", (rut,))
            existente = cur.fetchone()

            dispositivo_origen_id = None
            if not existente:
                device_mac = request.headers.get('X-Device-MAC', '').strip()
                if device_mac:
                    cur.execute(
                        "SELECT id FROM dispositivos WHERE REPLACE(mac_address, ':', '') = %s",
                        (device_mac,)
                    )
                    d_row = cur.fetchone()
                    if d_row:
                        dispositivo_origen_id = d_row[0]

                cur.execute(
                    "INSERT INTO personas (empresa_id, dispositivo_origen_id, nombre, rut) VALUES (NULL, %s, %s, %s) RETURNING id, nombre",
                    (dispositivo_origen_id, rut, rut)
                )
                row = cur.fetchone()
                persona_id = row[0]
                nombre_persona = row[1]
                conn.commit()

                if consentimiento:
                    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                    cur.execute(
                        "INSERT INTO consentimientos (persona_id, version_politica, ip_dispositivo, metodo_aceptacion) VALUES (%s, '1.0', %s, 'dispositivo') ON CONFLICT (persona_id) DO NOTHING",
                        (persona_id, ip)
                    )
                    conn.commit()
            else:
                persona_id = existente[0]
                nombre_persona = existente[1]

                if not _verificar_consentimiento(persona_id):
                    if consentimiento:
                        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                        cur.execute(
                            "INSERT INTO consentimientos (persona_id, version_politica, ip_dispositivo, metodo_aceptacion) VALUES (%s, '1.0', %s, 'dispositivo') ON CONFLICT (persona_id) DO NOTHING",
                            (persona_id, ip)
                        )
                        conn.commit()
                    else:
                        return jsonify({'error': 'Consentimiento biometrico requerido'}), 403

            preview_path = guardar_imagen_de_registro(persona_id, imagen_b64, suffix=f'_reg_{uuid.uuid4().hex[:4]}')
            quality_score = float(cv2.Laplacian(cv2.imread(preview_path, cv2.IMREAD_GRAYSCALE), cv2.CV_64F).var())
            encoding_json = cifrar_embedding(embedding_captura.tolist())

            cur.execute(
                "INSERT INTO encodings_faciales (persona_id, encoding, quality_score) VALUES (%s, %s, %s)",
                (persona_id, encoding_json, quality_score)
            )
            conn.commit()

            if os.path.exists(preview_path):
                os.unlink(preview_path)

            _invalidar_cache()
            _log_biometrico(persona_id, None, 'registro', 'exito')

            return jsonify({
                'ok': True,
                'persona_id': str(persona_id),
                'rut': rut,
                'nombre': nombre_persona,
                'registro_nuevo': existente is None
            })
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cur.close()
            conn.close()
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if preview_path and os.path.exists(preview_path):
            os.unlink(preview_path)
