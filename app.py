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

# Forzar flush inmediato de prints en Docker
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

# ===== Configuración =====
BROKER = os.getenv("BROKER_HOST", "mosquitto")
PORT = int(os.getenv("BROKER_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "test/#")
OUTPUT_DIR = "imagenes"

# ===== Variables para reconstruir imágenes =====
buffers = defaultdict(str)  # Almacena las partes de cada sesión
img_counter = 0
known_faces = {}  # Cache de rostros conocidos: {nombre: [encoding1, encoding2, ...]}
mqtt_client = None  # Cliente MQTT global para enviar respuestas

# ===== Crear carpeta =====
os.makedirs(OUTPUT_DIR, exist_ok=True)

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

# ===== Cliente MQTT =====
client = mqtt.Client()
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message

print("🚀 Iniciando receptor de mensajes MQTT...", flush=True)
print(f"🔗 Conectando a {BROKER}:{PORT}", flush=True)
print(f"📡 Escuchando tópico: {TOPIC}", flush=True)
print("\n⏳ Esperando mensajes...\n", flush=True)

try:
    client.connect(BROKER, PORT)
    client.loop_forever()
except KeyboardInterrupt:
    print("\n\n👋 Desconectando...")
    client.disconnect()
except Exception as e:
    print(f"❌ Error: {e}")