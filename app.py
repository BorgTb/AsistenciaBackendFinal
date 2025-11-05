import paho.mqtt.client as mqtt
import base64
import os
import face_recognition
import numpy as np
from datetime import datetime
import sys
import logging
import threading
from queue import Queue
from collections import defaultdict

# ===== Configuración de logging =====
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug.log')
    ]
)
logger = logging.getLogger(__name__)

# ===== Configuración =====
BROKER = os.getenv("BROKER_HOST", "mosquitto")
PORT = int(os.getenv("BROKER_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "test/imagenes/#")
OUTPUT_DIR = "imagenes"
KNOWN_DIR = "rostros"

# ===== Variables =====
buffer = ""
img_counter = 0
known_encodings = []
known_names = []
image_queue = Queue()  # Cola para procesar imágenes en paralelo
buffers = defaultdict(str)  # Buffer por sesión de imagen
lock = threading.Lock()  # Para evitar race conditions

# ===== Crear carpetas =====
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(KNOWN_DIR, exist_ok=True)

# ===== Cargar rostros conocidos =====
logger.info("🧠 Cargando rostros conocidos...")
for file in os.listdir(KNOWN_DIR):
    if file.lower().endswith((".jpg", ".png")):
        path = os.path.join(KNOWN_DIR, file)
        name = os.path.splitext(file)[0]
        image = face_recognition.load_image_file(path)
        encodings = face_recognition.face_encodings(image)
        if encodings:
            known_encodings.append(encodings[0])
            known_names.append(name)
            logger.info(f"✅ Cargado rostro: {name}")
        else:
            logger.warning(f"⚠️ No se detectó rostro en {file}")

logger.info(f"📚 Total rostros cargados: {len(known_names)}")

# ===== Callbacks MQTT =====
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"✅ Conectado al broker MQTT ({BROKER}:{PORT})")
        client.subscribe(TOPIC)
        logger.info(f"📡 Suscrito al tópico: {TOPIC}")
    else:
        logger.error(f"❌ Error de conexión MQTT, código: {rc}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning(f"⚠️ Desconexión inesperada. Código: {rc}")

def on_message(client, userdata, msg):
    global img_counter
    try:
        topic = msg.topic
        logger.debug(f"📨 Mensaje recibido en tópico: {topic}, tamaño: {len(msg.payload)} bytes")
        
        # Extrae el ID de sesión del tópico (ej: test/imagenes/sesion123/start)
        parts = topic.split('/')
        if len(parts) < 3:
            logger.warning(f"⚠️ Tópico inválido: {topic}")
            return
        
        session_id = parts[2]  # ID único de la sesión de imagen
        
        if topic.endswith("/start"):
            with lock:
                buffers[session_id] = ""
            logger.info(f"📥 Inicio de nueva imagen (sesión: {session_id})")

        elif topic.endswith("/part"):
            try:
                parte = msg.payload.decode('utf-8', errors='replace')
                with lock:
                    buffers[session_id] += parte
                logger.debug(f"Parte recibida (sesión: {session_id}), buffer: {len(buffers[session_id])} caracteres")
            except Exception as e:
                logger.error(f"❌ Error decodificando parte (sesión: {session_id}): {e}")

        elif topic.endswith("/end"):
            logger.info(f"💾 Imagen completa recibida (sesión: {session_id}), enviando a cola...")
            try:
                with lock:
                    buffer_data = buffers.pop(session_id, "")
                
                if not buffer_data:
                    logger.warning(f"⚠️ Buffer vacío para sesión: {session_id}")
                    return
                
                # Envía a la cola de procesamiento para hacerlo en paralelo
                with lock:
                    img_counter_local = img_counter
                    img_counter += 1
                
                image_queue.put({
                    'buffer': buffer_data,
                    'counter': img_counter_local,
                    'session_id': session_id
                })
                logger.debug(f"✅ Imagen añadida a cola de procesamiento (sesión: {session_id})")
                
            except Exception as e:
                logger.error(f"❌ Error en /end (sesión: {session_id}): {type(e).__name__}: {e}")
        else:
            logger.debug(f"📨 Mensaje en tópico no capturado: {topic}")
            
    except Exception as e:
        logger.error(f"❌ Error en on_message: {type(e).__name__}: {e}", exc_info=True)

# ===== Reconocimiento facial =====
def recognize_face(image_path):
    try:
        if not os.path.exists(image_path):
            logger.error(f"❌ Archivo no existe: {image_path}")
            return
        
        unknown_image = face_recognition.load_image_file(image_path)
        unknown_encodings = face_recognition.face_encodings(unknown_image)

        if not unknown_encodings:
            logger.warning(f"⚠️ No se detectaron rostros en: {os.path.basename(image_path)}")
            return

        unknown_encoding = unknown_encodings[0]
        results = face_recognition.compare_faces(known_encodings, unknown_encoding, tolerance=0.5)
        distances = face_recognition.face_distance(known_encodings, unknown_encoding)

        if len(distances) == 0:
            logger.warning("⚠️ No hay rostros conocidos para comparar")
            return

        if True in results:
            best_match = np.argmin(distances)
            confidence = 1 - distances[best_match]  # Confianza de 0 a 1
            name = known_names[best_match]
            confidence_pct = confidence * 100
            logger.info(f"✅ Rostro reconocido: {name} ({confidence_pct:.1f}% confianza) - {datetime.now().strftime('%H:%M:%S')}")
            
            # Registra en CSV
            with open("asistencia.csv", "a") as log:
                log.write(f"{datetime.now()}, {name}, {confidence_pct:.1f}%\n")
        else:
            closest_distance = np.min(distances)
            logger.info(f"❌ Rostro desconocido (distancia mínima: {closest_distance:.3f})")
            
    except Exception as e:
        logger.error(f"⚠️ Error en reconocimiento: {type(e).__name__}: {e}", exc_info=True)

# ===== Procesador de imágenes en cola =====
def image_processor():
    """Procesa imágenes de forma asincrónica desde la cola"""
    logger.info("🔄 Procesador de imágenes iniciado...")
    while True:
        try:
            # Espera a que haya una imagen en la cola
            item = image_queue.get(timeout=1)
            buffer_data = item['buffer']
            counter = item['counter']
            session_id = item['session_id']
            
            logger.debug(f"⏳ Procesando imagen {counter} de cola (sesión: {session_id})")
            
            try:
                img_data = base64.b64decode(buffer_data)
                filename = os.path.join(OUTPUT_DIR, f"imagen_{counter}.jpg")
                
                with open(filename, "wb") as f:
                    f.write(img_data)
                
                logger.info(f"✅ Imagen guardada: {filename}")
                recognize_face(filename)
                
            except Exception as e:
                logger.error(f"❌ Error procesando imagen {counter}: {type(e).__name__}: {e}")
            
            image_queue.task_done()
            
        except Exception as e:
            # timeout normal, continúa esperando
            pass

# ===== Cliente MQTT =====
client = mqtt.Client()
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message

# Inicia el thread de procesamiento de imágenes
processor_thread = threading.Thread(target=image_processor, daemon=True)
processor_thread.start()
logger.info("✅ Thread de procesamiento iniciado")

logger.info("🚀 Iniciando receptor MQTT con reconocimiento facial...")
try:
    client.connect(BROKER, PORT)
    logger.info(f"📡 Conectando a {BROKER}:{PORT}...")
    client.loop_forever()
except Exception as e:
    logger.error(f"❌ Error fatal: {type(e).__name__}: {e}", exc_info=True)