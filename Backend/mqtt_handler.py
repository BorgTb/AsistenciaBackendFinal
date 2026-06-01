import paho.mqtt.client as mqtt
import base64
import json
import os
import io
import time
import threading
from datetime import datetime, timezone
from PIL import Image
from deepface import DeepFace
from database import get_connection

buffer = []
current_persona_id = None
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1884

heartbeat_times = {}
heartbeat_lock = threading.Lock()

PREVIEWS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static', 'previews'))
os.makedirs(PREVIEWS_DIR, exist_ok=True)

def extraer_embedding_mqtt(img_path):
    resultado = DeepFace.represent(
        img_path=img_path,
        model_name="Facenet",
        enforce_detection=True,
        detector_backend="retinaface"
    )
    return resultado[0]['embedding']

def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print(f"❌ MQTT fallo conexion. Codigo: {rc}", flush=True)
        return

    print(f"🟢 MQTT conectado (rc={rc})", flush=True)
    client.subscribe("esp32/imagen/#")
    client.subscribe("esp32/asistencia/#")
    client.subscribe("esp32/heartbeat/#")
    client.subscribe("esp32/lwt/#")
    client.subscribe("esp32/imagen/registrar")  # ← agregar
    print("📡 Suscripciones registradas.", flush=True)

    # FIX: publicar el eco en un hilo separado con delay
    # para darle tiempo al loop de procesar la suscripcion
    def eco_delayed():
        time.sleep(0.5)
        client.publish("esp32/imagen/eco", "Python esta vivo")
        print("📢 Eco enviado.", flush=True)

    threading.Thread(target=eco_delayed, daemon=True).start()

def on_message(client, userdata, msg):
    global buffer, current_persona_id
    
    # Extraer el tópico completo de forma segura
    full_topic = str(msg.topic)
    
    # Imprimir CUALQUIER COSA que llegue para depuración
    print(f"📩 [MQTT] Recibido en: {full_topic} | Tamaño: {len(msg.payload)} bytes", flush=True)

    if full_topic == "esp32/imagen/eco":
        print("✅ ECO OK — Python se escucha a si mismo.", flush=True)
        return
    
    if full_topic == "esp32/imagen/registrar":
        try:
            payload = json.loads(msg.payload.decode())
            persona_id = payload.get("persona_id", "")
            imagen_b64 = payload.get("imagen", "")
            
            if not persona_id or not imagen_b64:
                print("❌ Mensaje de registro incompleto", flush=True)
                return
                
            print(f"📸 Registro facial recibido para ID: {persona_id}", flush=True)
            procesar_imagen_facial(client, persona_id, imagen_b64)
        except Exception as e:
            print(f"❌ Error procesando registro facial: {e}", flush=True)
        return

    if full_topic.startswith("esp32/heartbeat/"):
        mac = full_topic.split("/")[-1]
        with heartbeat_lock:
            heartbeat_times[mac] = time.time()
        try:
            payload = json.loads(msg.payload.decode() or '{}')
            ip = payload.get('ip', '')
            conn = get_connection()
            cur = conn.cursor()
            if ip:
                cur.execute(
                    "UPDATE dispositivos SET ultimo_heartbeat = NOW(), estado = 'activo', ip_local = %s WHERE REPLACE(mac_address, ':', '') = %s",
                    (ip, mac)
                )
            else:
                cur.execute(
                    "UPDATE dispositivos SET ultimo_heartbeat = NOW(), estado = 'activo' WHERE REPLACE(mac_address, ':', '') = %s",
                    (mac,)
                )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"❌ Error heartbeat DB: {e}", flush=True)
        return

    if full_topic.startswith("esp32/lwt/"):
        mac = full_topic.split("/")[-1]
        print(f"⚠️ LWT recibido: dispositivo {mac} desconectado", flush=True)
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE dispositivos SET estado = 'inactivo' WHERE REPLACE(mac_address, ':', '') = %s",
                (mac,)
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"❌ Error LWT DB: {e}", flush=True)
        return

    if full_topic == "esp32/imagen/start":
        buffer.clear()
        current_persona_id = msg.payload.decode().strip()
        print(f"📸 Inicio recepción para ID: '{current_persona_id}'", flush=True)

    elif full_topic == "esp32/imagen/part":
        buffer.append(msg.payload.decode())
        # Imprimir progreso cada 5 fragmentos
        if len(buffer) % 5 == 0:
            print(f"   ...recibidos {len(buffer)} fragmentos...", flush=True)

    elif full_topic == "esp32/imagen/end":
        print(f"🔚 'end' recibido. Total fragmentos: {len(buffer)} | ID: '{current_persona_id}'", flush=True)

        if not current_persona_id:
            print("⚠️ Error: 'end' recibido pero no hay ID activo.", flush=True)
            buffer.clear()
            return

        if len(buffer) == 0:
            print("⚠️ Error: Buffer vacío al recibir 'end'.", flush=True)
            current_persona_id = None
            return

        # 1. Unir y limpiar el Base64
        imagen_b64 = "".join(buffer).replace("\n", "").replace("\r", "").replace(" ", "")
        
        # 2. Reparar el final del JPEG (Truco vital)
        end_marker = "//Z"
        if end_marker in imagen_b64:
            imagen_b64 = imagen_b64.split(end_marker)[0] + end_marker
            
        # 3. Reparar el Padding de Base64
        padding_needed = len(imagen_b64) % 4
        if padding_needed:
            imagen_b64 += '=' * (4 - padding_needed)

        print(f"✅ Imagen ensamblada y lista para procesar: {len(imagen_b64)} chars", flush=True)
        
        # Llamar a la función de procesamiento
        procesar_imagen_facial(client, current_persona_id, imagen_b64)
        
        # Limpiar para el siguiente
        buffer.clear()
        current_persona_id = None

def procesar_imagen_facial(client, persona_id, imagen_b64):
    file_name = f"{persona_id}.jpg"
    file_path = os.path.join(PREVIEWS_DIR, file_name)

    try:
        try:
            img_bytes = base64.b64decode(imagen_b64, validate=True)
        except Exception:
            print("❌ Base64 invalido o corrupto.", flush=True)
            client.publish("esp32/respuesta/facial", json.dumps({
                "status": "error", "mensaje": "Base64 corrupto"
            }))
            return

        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img.save(file_path)
        print(f"💾 Imagen guardada: {file_path}", flush=True)

        print("🧠 Analizando con DeepFace...", flush=True)
        embedding = extraer_embedding_mqtt(file_path)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE personas SET encoding_facial = %s WHERE id = %s",
            (json.dumps(embedding), persona_id)
        )
        conn.commit()
        cur.close()
        conn.close()

        print(f"🎉 Rostro guardado en BD para ID {persona_id}", flush=True)
        client.publish("esp32/respuesta/facial", json.dumps({
            "status": "ok", "file_name": file_name
        }))

    except ValueError as ve:
        print(f"❌ DeepFace: {ve}", flush=True)
        client.publish("esp32/respuesta/facial", json.dumps({
            "status": "error", "mensaje": str(ve)
        }))
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        client.publish("esp32/respuesta/facial", json.dumps({
            "status": "error", "mensaje": str(e)
        }))

def start_mqtt():
    try:
        print(f"🚀 Conectando MQTT a {BROKER_HOST}:{BROKER_PORT}...", flush=True)
        client = mqtt.Client(client_id="python-backend", clean_session=True)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER_HOST, BROKER_PORT, 60)
        client.loop_start()
        threading.Thread(target=device_watchdog, daemon=True).start()
        return client
    except Exception as e:
        print(f"❌ ERROR CRITICO MQTT: {e}", flush=True)
        return None

HEARTBEAT_TIMEOUT = 90

def device_watchdog():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE dispositivos SET estado = 'inactivo' WHERE mac_address IS NOT NULL AND mac_address != ''")
        conn.commit()
        cur.close()
        conn.close()
        print("🔌 Inicial: todos los dispositivos marcados inactivos (esperando heartbeat)", flush=True)
    except Exception as e:
        print(f"❌ Error sweep inicial: {e}", flush=True)

    while True:
        time.sleep(60)
        ahora = time.time()
        with heartbeat_lock:
            vencidos = [mac for mac, t in heartbeat_times.items() if (ahora - t) > HEARTBEAT_TIMEOUT]
        for mac in vencidos:
            print(f"⏱ Watchdog: dispositivo {mac} sin heartbeat por >{HEARTBEAT_TIMEOUT}s", flush=True)
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE dispositivos SET estado = 'inactivo' WHERE REPLACE(mac_address, ':', '') = %s",
                    (mac,)
                )
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"❌ Error watchdog DB: {e}", flush=True)