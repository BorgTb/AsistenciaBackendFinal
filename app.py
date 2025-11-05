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
        
        # ===== TÓPICO DE REGISTRO: test/registro/nombre/start|part|end =====
        if topic.startswith("test/registro/"):
            parts = topic.split('/')
            if len(parts) < 4:
                logger.warning(f"⚠️ Tópico inválido: {topic}")
                return
            
            person_name = parts[2]  # Nombre de la persona
            action = parts[3]       # start, part, end
            session_id = f"reg_{person_name}_{datetime.now().strftime('%H%M%S')}"
            
            if action == "start":
                with lock:
                    buffers[session_id] = ""
                logger.info(f"📥 Registro iniciado para: {person_name}")
            
            elif action == "part":
                try:
                    parte = msg.payload.decode('utf-8', errors='replace')
                    with lock:
                        buffers[session_id] += parte
                    logger.debug(f"Parte recibida (registro: {person_name})")
                except Exception as e:
                    logger.error(f"❌ Error decodificando parte: {e}")
            
            elif action == "end":
                logger.info(f"💾 Registro completado para: {person_name}")
                try:
                    with lock:
                        buffer_data = buffers.pop(session_id, "")
                    
                    if not buffer_data:
                        logger.warning(f"⚠️ Buffer vacío para: {person_name}")
                        return
                    
                    with lock:
                        img_counter_local = img_counter
                        img_counter += 1
                    
                    image_queue.put({
                        'buffer': buffer_data,
                        'counter': img_counter_local,
                        'session_id': session_id,
                        'type': 'register',
                        'person_name': person_name
                    })
                    logger.debug(f"✅ Imagen de registro añadida a cola")
                    
                except Exception as e:
                    logger.error(f"❌ Error en registro: {type(e).__name__}: {e}")
        
        # ===== TÓPICO DE RECONOCIMIENTO: test/imagenes/sesion/start|part|end =====
        elif topic.startswith("test/imagenes/"):
            parts = topic.split('/')
            if len(parts) < 3:
                logger.warning(f"⚠️ Tópico inválido: {topic}")
                return
            
            session_id = parts[2]
            
            if topic.endswith("/start"):
                with lock:
                    buffers[session_id] = ""
                logger.info(f"📥 Reconocimiento iniciado (sesión: {session_id})")

            elif topic.endswith("/part"):
                try:
                    parte = msg.payload.decode('utf-8', errors='replace')
                    with lock:
                        buffers[session_id] += parte
                    logger.debug(f"Parte recibida (sesión: {session_id})")
                except Exception as e:
                    logger.error(f"❌ Error decodificando parte: {e}")

            elif topic.endswith("/end"):
                logger.info(f"💾 Reconocimiento completo (sesión: {session_id})")
                try:
                    with lock:
                        buffer_data = buffers.pop(session_id, "")
                    
                    if not buffer_data:
                        logger.warning(f"⚠️ Buffer vacío para sesión: {session_id}")
                        return
                    
                    with lock:
                        img_counter_local = img_counter
                        img_counter += 1
                    
                    image_queue.put({
                        'buffer': buffer_data,
                        'counter': img_counter_local,
                        'session_id': session_id,
                        'type': 'recognition'
                    })
                    logger.debug(f"✅ Imagen de reconocimiento añadida a cola")
                    
                except Exception as e:
                    logger.error(f"❌ Error: {type(e).__name__}: {e}")
            
    except Exception as e:
        logger.error(f"❌ Error en on_message: {type(e).__name__}: {e}", exc_info=True)

# ===== Reconocimiento facial =====
def recognize_face(image_path):
    try:
        if not os.path.exists(image_path):
            logger.error(f"❌ Archivo no existe: {image_path}")
            return None, 0
        
        unknown_image = face_recognition.load_image_file(image_path)
        unknown_encodings = face_recognition.face_encodings(unknown_image)

        if not unknown_encodings:
            logger.warning(f"⚠️ No se detectaron rostros en: {os.path.basename(image_path)}")
            return None, 0

        unknown_encoding = unknown_encodings[0]
        results = face_recognition.compare_faces(known_encodings, unknown_encoding, tolerance=0.5)
        distances = face_recognition.face_distance(known_encodings, unknown_encoding)

        if len(distances) == 0:
            logger.warning("⚠️ No hay rostros conocidos para comparar")
            return None, 0

        if True in results:
            best_match = np.argmin(distances)
            confidence = 1 - distances[best_match]  # Confianza de 0 a 1
            name = known_names[best_match]
            confidence_pct = confidence * 100
            logger.info(f"✅ Rostro reconocido: {name} ({confidence_pct:.1f}% confianza) - {datetime.now().strftime('%H:%M:%S')}")
            
            # Registra en CSV
            with open("asistencia.csv", "a") as log:
                log.write(f"{datetime.now()}, {name}, {confidence_pct:.1f}%\n")
            
            return name, confidence_pct
        else:
            closest_distance = np.min(distances)
            logger.info(f"❌ Rostro desconocido (distancia mínima: {closest_distance:.3f})")
            return None, 0
            
    except Exception as e:
        logger.error(f"⚠️ Error en reconocimiento: {type(e).__name__}: {e}", exc_info=True)
        return None, 0

# ===== Registrar nuevo rostro =====
def register_face(image_path, person_name):
    """Registra un nuevo rostro en la carpeta known_dir"""
    try:
        if not os.path.exists(image_path):
            logger.error(f"❌ Archivo no existe: {image_path}")
            return False, "Archivo no existe"
        
        # Cargar imagen y detectar rostro
        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        
        if not encodings:
            logger.warning(f"⚠️ No se detectó rostro en la imagen para: {person_name}")
            return False, "No se detectó ningún rostro en la imagen"
        
        if len(encodings) > 1:
            logger.warning(f"⚠️ Se detectaron múltiples rostros. Usando el primero para: {person_name}")
        
        # Guardar la imagen en carpeta rostros
        filename = f"{person_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(KNOWN_DIR, filename)
        
        # Copiar imagen
        import shutil
        shutil.copy(image_path, filepath)
        
        # Agregar a la lista de rostros conocidos
        encoding = encodings[0]
        with lock:
            known_encodings.append(encoding)
            known_names.append(person_name)
        
        logger.info(f"✅ Rostro registrado: {person_name} ({filename})")
        return True, f"✅ {person_name} registrado exitosamente"
        
    except Exception as e:
        logger.error(f"❌ Error registrando rostro: {type(e).__name__}: {e}")
        return False, f"Error: {str(e)}"

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
            img_type = item.get('type', 'recognition')  # 'recognition' o 'register'
            person_name = item.get('person_name', None)  # Para registro
            
            logger.debug(f"⏳ Procesando imagen {counter} de cola (sesión: {session_id}, tipo: {img_type})")
            
            try:
                img_data = base64.b64decode(buffer_data)
                filename = os.path.join(OUTPUT_DIR, f"imagen_{counter}.jpg")
                
                with open(filename, "wb") as f:
                    f.write(img_data)
                
                logger.info(f"✅ Imagen guardada: {filename}")
                
                # ===== Procesar según tipo =====
                if img_type == 'recognition':
                    recognize_face(filename)
                elif img_type == 'register' and person_name:
                    success, msg = register_face(filename, person_name)
                    logger.info(f"Registro: {msg}")
                
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