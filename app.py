import paho.mqtt.client as mqtt
import os
from datetime import datetime
import sys
import base64
from collections import defaultdict
import face_recognition
import numpy as np
from PIL import Image
import io
import glob
import csv
from flask import Flask, jsonify, request
from flask_cors import CORS
import threading

# Forzar flush inmediato de prints en Docker
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

# ===== Configuración =====
BROKER = os.getenv("BROKER_HOST", "mosquitto")
PORT = int(os.getenv("BROKER_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "test/#")
OUTPUT_DIR = "imagenes"
DATA_DIR = "data"
PERSONAS_CSV = os.path.join(DATA_DIR, "personas.csv")
TURNOS_CSV = os.path.join(DATA_DIR, "turnos.csv")
ASIGNACIONES_CSV = os.path.join(DATA_DIR, "asignaciones.csv")
DISPOSITIVOS_CSV = os.path.join(DATA_DIR, "dispositivos.csv")

# ===== Variables para reconstruir imágenes =====
buffers = defaultdict(str)  # Almacena las partes de cada sesión
img_counter = 0
known_faces = {}  # Cache de rostros conocidos: {nombre: [encoding1, encoding2, ...]}
mqtt_client = None  # Cliente MQTT global para enviar respuestas

# ===== Flask App =====
app = Flask(__name__)
CORS(app)

# ===== Crear carpetas =====
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ===== Inicializar CSVs =====
def init_csv_files():
    """Inicializa los archivos CSV con sus encabezados si no existen"""
    
    # personas.csv: id, nombre, fecha_registro, total_imagenes
    if not os.path.exists(PERSONAS_CSV):
        with open(PERSONAS_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'nombre', 'fecha_registro', 'total_imagenes'])
        print("✅ Archivo personas.csv creado", flush=True)
    
    # turnos.csv: id, nombre_turno, hora_inicio, hora_fin, dias_semana
    if not os.path.exists(TURNOS_CSV):
        with open(TURNOS_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'nombre_turno', 'hora_inicio', 'hora_fin', 'dias_semana'])
            # Turnos por defecto
            writer.writerow(['1', 'Mañana', '08:00', '16:00', 'L,M,X,J,V'])
            writer.writerow(['2', 'Tarde', '16:00', '00:00', 'L,M,X,J,V'])
            writer.writerow(['3', 'Noche', '00:00', '08:00', 'L,M,X,J,V'])
        print("✅ Archivo turnos.csv creado con turnos por defecto", flush=True)
    
    # asignaciones.csv: persona_id, turno_id, fecha_asignacion
    if not os.path.exists(ASIGNACIONES_CSV):
        with open(ASIGNACIONES_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['persona_id', 'turno_id', 'fecha_asignacion'])
        print("✅ Archivo asignaciones.csv creado", flush=True)
    
    # dispositivos.csv: id, nombre, ip, estado, ultima_conexion
    if not os.path.exists(DISPOSITIVOS_CSV):
        with open(DISPOSITIVOS_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'nombre', 'ip', 'estado', 'deteccion_auto', 'ultima_conexion'])
        print("✅ Archivo dispositivos.csv creado", flush=True)

init_csv_files()

# ===== Funciones CSV =====
def get_all_personas():
    """Obtiene todas las personas registradas"""
    personas = []
    try:
        with open(PERSONAS_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                personas.append(row)
    except Exception as e:
        print(f"Error leyendo personas: {e}", flush=True)
    return personas

def get_persona_by_nombre(nombre):
    """Obtiene una persona por su nombre"""
    personas = get_all_personas()
    for persona in personas:
        if persona['nombre'].lower() == nombre.lower():
            return persona
    return None

def add_persona(nombre):
    """Agrega una nueva persona al CSV"""
    personas = get_all_personas()
    nuevo_id = str(len(personas) + 1)
    fecha_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(PERSONAS_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([nuevo_id, nombre, fecha_registro, '1'])
    
    print(f"✅ Persona agregada al CSV: {nombre} (ID: {nuevo_id})", flush=True)
    return nuevo_id

def update_persona_imagenes(nombre):
    """Actualiza el contador de imágenes de una persona"""
    personas = get_all_personas()
    updated = []
    
    for persona in personas:
        if persona['nombre'].lower() == nombre.lower():
            persona['total_imagenes'] = str(int(persona['total_imagenes']) + 1)
        updated.append(persona)
    
    # Reescribir CSV
    with open(PERSONAS_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'nombre', 'fecha_registro', 'total_imagenes'])
        writer.writeheader()
        writer.writerows(updated)

def get_all_turnos():
    """Obtiene todos los turnos disponibles"""
    turnos = []
    try:
        with open(TURNOS_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                turnos.append(row)
    except Exception as e:
        print(f"Error leyendo turnos: {e}", flush=True)
    return turnos

def get_asignaciones():
    """Obtiene todas las asignaciones de turnos"""
    asignaciones = []
    try:
        with open(ASIGNACIONES_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                asignaciones.append(row)
    except Exception as e:
        print(f"Error leyendo asignaciones: {e}", flush=True)
    return asignaciones

def asignar_turno(persona_id, turno_id):
    """Asigna un turno a una persona"""
    fecha_asignacion = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Verificar si ya existe la asignación
    asignaciones = get_asignaciones()
    for asig in asignaciones:
        if asig['persona_id'] == persona_id and asig['turno_id'] == turno_id:
            return False  # Ya existe
    
    with open(ASIGNACIONES_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([persona_id, turno_id, fecha_asignacion])
    
    print(f"✅ Turno {turno_id} asignado a persona {persona_id}", flush=True)
    return True

def get_turnos_persona(persona_id):
    """Obtiene los turnos asignados a una persona"""
    asignaciones = get_asignaciones()
    turnos = get_all_turnos()
    
    turnos_persona = []
    for asig in asignaciones:
        if asig['persona_id'] == persona_id:
            for turno in turnos:
                if turno['id'] == asig['turno_id']:
                    turno_info = turno.copy()
                    turno_info['fecha_asignacion'] = asig['fecha_asignacion']
                    turnos_persona.append(turno_info)
    
    return turnos_persona

def get_all_dispositivos():
    """Obtiene todos los dispositivos registrados"""
    dispositivos = []
    try:
        with open(DISPOSITIVOS_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                dispositivos.append(row)
    except Exception as e:
        print(f"Error leyendo dispositivos: {e}", flush=True)
    return dispositivos

def registrar_dispositivo(ip, nombre="ESP32-CAM"):
    """Registra o actualiza un dispositivo"""
    dispositivos = get_all_dispositivos()
    fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Buscar si ya existe
    existe = False
    for disp in dispositivos:
        if disp['ip'] == ip:
            disp['ultima_conexion'] = fecha_actual
            disp['estado'] = 'online'
            existe = True
            break
    
    if not existe:
        nuevo_id = str(len(dispositivos) + 1)
        dispositivos.append({
            'id': nuevo_id,
            'nombre': nombre,
            'ip': ip,
            'estado': 'online',
            'deteccion_auto': 'false',
            'ultima_conexion': fecha_actual
        })
    
    # Reescribir CSV
    with open(DISPOSITIVOS_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'nombre', 'ip', 'estado', 'deteccion_auto', 'ultima_conexion'])
        writer.writeheader()
        writer.writerows(dispositivos)
    
    print(f"✅ Dispositivo registrado: {ip} ({nombre})", flush=True)
    return True

def actualizar_estado_dispositivo(ip, deteccion_auto=None):
    """Actualiza el estado de detección automática de un dispositivo"""
    dispositivos = get_all_dispositivos()
    
    for disp in dispositivos:
        if disp['ip'] == ip:
            if deteccion_auto is not None:
                disp['deteccion_auto'] = 'true' if deteccion_auto else 'false'
            disp['ultima_conexion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            break
    
    # Reescribir CSV
    with open(DISPOSITIVOS_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'nombre', 'ip', 'estado', 'deteccion_auto', 'ultima_conexion'])
        writer.writeheader()
        writer.writerows(dispositivos)

# ===== Funciones auxiliares =====
def load_known_faces():
    """Carga todos los rostros conocidos de la carpeta imagenes"""
    global known_faces
    known_faces = {}
    
    print("🧠 Cargando rostros conocidos...", flush=True)
    image_files = glob.glob(os.path.join(OUTPUT_DIR, "*.jpg"))
    
    for image_path in image_files:
        try:
            # Extraer nombre del archivo (formato: nombre_timestamp.jpg)
            filename = os.path.basename(image_path)
            person_name = filename.rsplit('_', 1)[0]  # Quitar timestamp
            
            # Cargar y codificar rostro
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            
            if encodings:
                if person_name not in known_faces:
                    known_faces[person_name] = []
                known_faces[person_name].append(encodings[0])
                print(f"  ✅ Cargado: {person_name}", flush=True)
        except Exception as e:
            print(f"  ⚠️ Error cargando {filename}: {e}", flush=True)
    
    print(f"📚 Total personas registradas: {len(known_faces)}", flush=True)
    return known_faces

def is_face_registered(face_encoding, person_name):
    """Verifica si un rostro ya está registrado"""
    if person_name not in known_faces:
        return False
    
    # Comparar con todos los encodings de esa persona
    for known_encoding in known_faces[person_name]:
        matches = face_recognition.compare_faces([known_encoding], face_encoding, tolerance=0.6)
        if matches[0]:
            return True
    
    return False

def recognize_face(face_encoding):
    """Identifica a qué persona pertenece un rostro"""
    if not known_faces:
        return None, 0
    
    best_match_name = None
    best_confidence = 0
    
    for person_name, encodings_list in known_faces.items():
        for known_encoding in encodings_list:
            # Calcular distancia
            face_distance = face_recognition.face_distance([known_encoding], face_encoding)[0]
            confidence = 1 - face_distance  # Convertir distancia a confianza (0-1)
            
            if confidence > best_confidence and confidence > 0.4:  # Umbral mínimo de confianza
                best_confidence = confidence
                best_match_name = person_name
    
    return best_match_name, best_confidence * 100  # Retornar porcentaje

def send_response(person_name, status, message):
    """Envía respuesta al ESP32 via MQTT"""
    if mqtt_client:
        topic = f"test/respuesta/{person_name}"
        payload = f"{status}|{message}"
        mqtt_client.publish(topic, payload)
        print(f"📤 Respuesta enviada a ESP32: {topic} -> {message}", flush=True)

# Cargar rostros al iniciar
load_known_faces()

# ===== Callbacks MQTT =====
def on_connect(client, userdata, flags, rc):
    global mqtt_client
    mqtt_client = client  # Guardar referencia global
    if rc == 0:
        print(f"✅ Conectado al broker MQTT ({BROKER}:{PORT})")
        client.subscribe(TOPIC)
        print(f"📡 Suscrito al tópico: {TOPIC}")
    else:
        print(f"❌ Error de conexión MQTT, código: {rc}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"⚠️ Desconexión inesperada. Código: {rc}")

def on_message(client, userdata, msg):
    """Procesa los mensajes recibidos y reconstruye imágenes"""
    global img_counter
    
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    topic = msg.topic
    
    print(f"🔔 ¡MENSAJE RECIBIDO!", flush=True)
    
    # Intentar decodificar el payload
    try:
        payload = msg.payload.decode('utf-8')
        payload_preview = payload[:100] + "..." if len(payload) > 100 else payload
    except:
        payload_preview = f"[Datos binarios: {len(msg.payload)} bytes]"
    
    # Mostrar mensaje
    print(f"\n{'='*60}", flush=True)
    print(f"⏰ Tiempo: {timestamp}", flush=True)
    print(f"📍 Tópico: {topic}", flush=True)
    print(f"📦 Tamaño: {len(msg.payload)} bytes", flush=True)
    print(f"📄 Contenido: {payload_preview}", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    # ===== PROCESAR IMÁGENES =====
    # Formato: test/registro/nombre/start|part|end
    if "/start" in topic:
        # Extraer identificador de sesión (ej: "registro_agustin")
        parts = topic.split('/')
        session_id = "_".join(parts[1:3])  # ej: "registro_agustin"
        buffers[session_id] = ""
        print(f"📥 Iniciando captura de imagen: {session_id}", flush=True)
    
    elif "/part" in topic:
        # Acumular partes
        parts = topic.split('/')
        session_id = "_".join(parts[1:3])
        try:
            parte = msg.payload.decode('utf-8')
            buffers[session_id] += parte
            print(f"📦 Parte recibida para: {session_id} (total: {len(buffers[session_id])} chars)", flush=True)
        except Exception as e:
            print(f"❌ Error decodificando parte: {e}", flush=True)
    
    elif "/end" in topic:
        # Guardar imagen completa
        parts = topic.split('/')
        session_id = "_".join(parts[1:3])
        
        if session_id in buffers:
            buffer_data = buffers.pop(session_id)
            
            if buffer_data:
                try:
                    # Decodificar Base64
                    img_data = base64.b64decode(buffer_data)
                    
                    # 🔍 DETECTAR ROSTRO ANTES DE GUARDAR
                    print(f"🔍 Analizando imagen con face_recognition...", flush=True)
                    
                    # Cargar imagen desde bytes
                    image = Image.open(io.BytesIO(img_data))
                    image_np = np.array(image)
                    
                    # Detectar rostros y obtener encodings
                    face_locations = face_recognition.face_locations(image_np)
                    face_encodings = face_recognition.face_encodings(image_np, face_locations)
                    
                    if len(face_locations) == 0:
                        print(f"⚠️ No se detectó ningún rostro. Imagen NO guardada.", flush=True)
                        return
                    
                    if len(face_encodings) == 0:
                        print(f"⚠️ No se pudo codificar el rostro. Imagen NO guardada.", flush=True)
                        return
                    
                    print(f"✅ Detectados {len(face_locations)} rostro(s)!", flush=True)
                    
                    # Obtener nombre de la persona
                    person_name = parts[2] if len(parts) > 2 else "desconocido"
                    
                    # 🔒 VERIFICAR SI YA ESTÁ REGISTRADO
                    face_encoding = face_encodings[0]  # Tomar el primer rostro
                    
                    if is_face_registered(face_encoding, person_name):
                        print(f"⚠️ El rostro de '{person_name}' YA está registrado. NO se guardó.", flush=True)
                        send_response(person_name, "DUPLICADO", f"El rostro de {person_name} ya esta registrado")
                        return
                    
                    # 🔍 INTENTAR RECONOCER SI ES OTRA PERSONA CONOCIDA
                    recognized_name, confidence = recognize_face(face_encoding)
                    if recognized_name and recognized_name != person_name:
                        print(f"⚠️ Este rostro pertenece a '{recognized_name}' ({confidence:.1f}% confianza)", flush=True)
                        send_response(person_name, "ERROR", f"Este rostro pertenece a {recognized_name} ({confidence:.0f}%)")
                        return
                    
                    # Guardar imagen
                    filename = f"{person_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    filepath = os.path.join(OUTPUT_DIR, filename)
                    
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    
                    # Agregar al cache de rostros conocidos
                    if person_name not in known_faces:
                        known_faces[person_name] = []
                    known_faces[person_name].append(face_encoding)
                    
                    # Agregar o actualizar en CSV
                    persona = get_persona_by_nombre(person_name)
                    if persona:
                        update_persona_imagenes(person_name)
                    else:
                        add_persona(person_name)
                    
                    img_counter += 1
                    print(f"💾 ¡NUEVO ROSTRO REGISTRADO!", flush=True)
                    print(f"📁 Guardado: {filepath} ({len(img_data)} bytes)", flush=True)
                    print(f"👤 Persona: {person_name}", flush=True)
                    print(f"📍 Posición rostro: {face_locations[0]}", flush=True)
                    
                    # 📤 ENVIAR RESPUESTA DE ÉXITO
                    send_response(person_name, "REGISTRADO", f"{person_name} registrado exitosamente!")
                    
                except Exception as e:
                    print(f"❌ Error procesando imagen: {e}", flush=True)
            else:
                print(f"⚠️ Buffer vacío para: {session_id}", flush=True)
        else:
            print(f"⚠️ No se encontró sesión: {session_id}", flush=True)

# ===== RUTAS API FLASK =====
@app.route('/api/personas', methods=['GET'])
def api_get_personas():
    """Obtiene la lista de todas las personas registradas"""
    try:
        personas = get_all_personas()
        return jsonify({
            'success': True,
            'total': len(personas),
            'personas': personas
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/personas/<persona_id>', methods=['GET'])
def api_get_persona(persona_id):
    """Obtiene información detallada de una persona incluyendo sus turnos"""
    try:
        personas = get_all_personas()
        persona = None
        for p in personas:
            if p['id'] == persona_id:
                persona = p
                break
        
        if not persona:
            return jsonify({'success': False, 'error': 'Persona no encontrada'}), 404
        
        # Obtener turnos asignados
        turnos = get_turnos_persona(persona_id)
        persona['turnos'] = turnos
        
        return jsonify({
            'success': True,
            'persona': persona
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/turnos', methods=['GET'])
def api_get_turnos():
    """Obtiene todos los turnos disponibles"""
    try:
        turnos = get_all_turnos()
        return jsonify({
            'success': True,
            'total': len(turnos),
            'turnos': turnos
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/turnos', methods=['POST'])
def api_create_turno():
    """Crea un nuevo turno"""
    try:
        data = request.json
        nombre_turno = data.get('nombre_turno')
        hora_inicio = data.get('hora_inicio')
        hora_fin = data.get('hora_fin')
        dias_semana = data.get('dias_semana', 'L,M,X,J,V')
        
        if not all([nombre_turno, hora_inicio, hora_fin]):
            return jsonify({'success': False, 'error': 'Faltan campos requeridos'}), 400
        
        turnos = get_all_turnos()
        nuevo_id = str(len(turnos) + 1)
        
        with open(TURNOS_CSV, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([nuevo_id, nombre_turno, hora_inicio, hora_fin, dias_semana])
        
        return jsonify({
            'success': True,
            'message': 'Turno creado exitosamente',
            'turno_id': nuevo_id
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/asignaciones', methods=['POST'])
def api_asignar_turno():
    """Asigna un turno a una persona"""
    try:
        data = request.json
        persona_id = data.get('persona_id')
        turno_id = data.get('turno_id')
        
        if not all([persona_id, turno_id]):
            return jsonify({'success': False, 'error': 'Faltan campos requeridos'}), 400
        
        # Verificar que existan persona y turno
        personas = get_all_personas()
        turnos = get_all_turnos()
        
        persona_existe = any(p['id'] == persona_id for p in personas)
        turno_existe = any(t['id'] == turno_id for t in turnos)
        
        if not persona_existe:
            return jsonify({'success': False, 'error': 'Persona no encontrada'}), 404
        if not turno_existe:
            return jsonify({'success': False, 'error': 'Turno no encontrado'}), 404
        
        # Asignar turno
        resultado = asignar_turno(persona_id, turno_id)
        
        if resultado:
            return jsonify({
                'success': True,
                'message': 'Turno asignado exitosamente'
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': 'La asignación ya existe'
            }), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/asignaciones', methods=['GET'])
def api_get_asignaciones():
    """Obtiene todas las asignaciones con información completa"""
    try:
        asignaciones = get_asignaciones()
        personas = get_all_personas()
        turnos = get_all_turnos()
        
        # Enriquecer asignaciones con información completa
        asignaciones_completas = []
        for asig in asignaciones:
            persona = next((p for p in personas if p['id'] == asig['persona_id']), None)
            turno = next((t for t in turnos if t['id'] == asig['turno_id']), None)
            
            if persona and turno:
                asignaciones_completas.append({
                    'persona': persona,
                    'turno': turno,
                    'fecha_asignacion': asig['fecha_asignacion']
                })
        
        return jsonify({
            'success': True,
            'total': len(asignaciones_completas),
            'asignaciones': asignaciones_completas
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/asignaciones/<persona_id>/<turno_id>', methods=['DELETE'])
def api_eliminar_asignacion(persona_id, turno_id):
    """Elimina una asignación de turno"""
    try:
        asignaciones = get_asignaciones()
        asignaciones_filtradas = [
            asig for asig in asignaciones 
            if not (asig['persona_id'] == persona_id and asig['turno_id'] == turno_id)
        ]
        
        if len(asignaciones) == len(asignaciones_filtradas):
            return jsonify({'success': False, 'error': 'Asignación no encontrada'}), 404
        
        # Reescribir CSV sin la asignación eliminada
        with open(ASIGNACIONES_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['persona_id', 'turno_id', 'fecha_asignacion'])
            writer.writeheader()
            writer.writerows(asignaciones_filtradas)
        
        return jsonify({
            'success': True,
            'message': 'Asignación eliminada exitosamente'
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def api_health():
    """Endpoint de health check"""
    return jsonify({
        'success': True,
        'status': 'running',
        'mqtt_connected': mqtt_client is not None and mqtt_client.is_connected(),
        'total_personas': len(get_all_personas()),
        'total_turnos': len(get_all_turnos())
    }), 200

@app.route('/api/dispositivos', methods=['GET'])
def api_get_dispositivos():
    """Obtiene todos los dispositivos registrados"""
    try:
        dispositivos = get_all_dispositivos()
        return jsonify({
            'success': True,
            'total': len(dispositivos),
            'dispositivos': dispositivos
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dispositivos/<dispositivo_id>', methods=['GET'])
def api_get_dispositivo(dispositivo_id):
    """Obtiene información de un dispositivo específico"""
    try:
        dispositivos = get_all_dispositivos()
        dispositivo = next((d for d in dispositivos if d['id'] == dispositivo_id), None)
        
        if not dispositivo:
            return jsonify({'success': False, 'error': 'Dispositivo no encontrado'}), 404
        
        return jsonify({
            'success': True,
            'dispositivo': dispositivo
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dispositivos/control', methods=['POST'])
def api_control_dispositivo():
    """Controla un dispositivo ESP32 remotamente via HTTP"""
    try:
        import requests
        
        data = request.json
        ip = data.get('ip')
        accion = data.get('accion')  # 'registro', 'auto-detect', 'status'
        parametros = data.get('parametros', {})
        
        if not ip or not accion:
            return jsonify({'success': False, 'error': 'Faltan campos requeridos'}), 400
        
        # Construir URL del ESP32
        esp_url = f"http://{ip}"
        
        if accion == 'auto-detect':
            response = requests.get(f"{esp_url}/auto-detect", timeout=5)
        elif accion == 'registro' and parametros.get('nombre'):
            nombre = parametros['nombre']
            response = requests.get(f"{esp_url}/register?nombre={nombre}", timeout=5)
        elif accion == 'status':
            response = requests.get(f"{esp_url}/status", timeout=5)
        else:
            return jsonify({'success': False, 'error': 'Acción no válida'}), 400
        
        # Registrar actividad del dispositivo
        registrar_dispositivo(ip)
        
        return jsonify({
            'success': True,
            'mensaje': f'Comando {accion} enviado al dispositivo {ip}',
            'respuesta': response.text
        }), 200
        
    except requests.Timeout:
        return jsonify({'success': False, 'error': 'Timeout - dispositivo no responde'}), 504
    except requests.ConnectionError:
        return jsonify({'success': False, 'error': 'No se puede conectar al dispositivo'}), 503
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dispositivos/register', methods=['POST'])
def api_register_dispositivo():
    """Registra un nuevo dispositivo ESP32"""
    try:
        data = request.json
        ip = data.get('ip')
        nombre = data.get('nombre', 'ESP32-CAM')
        
        if not ip:
            return jsonify({'success': False, 'error': 'IP es requerida'}), 400
        
        registrar_dispositivo(ip, nombre)
        
        return jsonify({
            'success': True,
            'message': f'Dispositivo {nombre} registrado en {ip}'
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== Cliente MQTT =====
client = mqtt.Client()
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message

def start_mqtt():
    """Inicia el cliente MQTT en un thread separado"""
    print("🚀 Iniciando receptor de mensajes MQTT...", flush=True)
    print(f"🔗 Conectando a {BROKER}:{PORT}", flush=True)
    print(f"📡 Escuchando tópico: {TOPIC}", flush=True)
    print("\n⏳ Esperando mensajes MQTT...\n", flush=True)
    
    try:
        client.connect(BROKER, PORT)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Desconectando MQTT...")
        client.disconnect()
    except Exception as e:
        print(f"❌ Error MQTT: {e}")

# ===== INICIAR SERVICIOS =====
if __name__ == "__main__":
    # Iniciar MQTT en un thread separado
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()
    
    print("\n" + "="*60, flush=True)
    print("🌐 Iniciando API Flask...", flush=True)
    print("📡 API disponible en: http://0.0.0.0:5000", flush=True)
    print("="*60 + "\n", flush=True)
    
    # Iniciar Flask en el thread principal
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)