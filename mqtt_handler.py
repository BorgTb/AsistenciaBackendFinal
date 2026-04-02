import paho.mqtt.client as mqtt
import base64
import json
import os
import io
from PIL import Image
from deepface import DeepFace
from database import get_connection

buffer = []
current_persona_id = None
# Cambiamos localhost por 127.0.0.1 para evitar conflictos de IPv4/IPv6 en Docker
BROKER_HOST = "127.0.0.1" 
BROKER_PORT = 1883

PREVIEWS_DIR = os.path.join(os.getcwd(), 'static', 'previews')
os.makedirs(PREVIEWS_DIR, exist_ok=True)

def on_connect(client, userdata, flags, rc):
    print(f"🟢 MQTT conectado exitosamente (Código: {rc})", flush=True)
    client.subscribe("esp32/imagen/#")
    client.subscribe("esp32/asistencia/#")
    
    # PRUEBA DE ECO: Python se envía un mensaje a sí mismo al instante de conectar
    print("📢 Enviando prueba de eco a Mosquitto...", flush=True)
    client.publish("esp32/imagen/eco", "Python esta vivo")

def on_message(client, userdata, msg):
    global buffer, current_persona_id
    topic = msg.topic.split("/")[-1]
    
    # ESTE PRINT ES NUEVO: Nos avisará de cualquier cosa que toque el broker
    #print(f"📩 [NUEVO MENSAJE] Tópico: {msg.topic} | Tamaño: {len(msg.payload)} bytes", flush=True)

    if topic == "eco":
        print("✅ PRUEBA DE ECO EXITOSA. Python se escucha a sí mismo.", flush=True)
        return

    if topic == "start":
        buffer.clear()
        current_persona_id = msg.payload.decode()
        print(f"📸 Iniciando recepción MQTT para Persona ID: {current_persona_id}", flush=True)

    elif topic == "part":
        buffer.append(msg.payload.decode())

    elif topic == "end":
        imagen_b64 = "".join(buffer)
        print(f"✅ Imagen ensamblada. Tamaño Base64: {len(imagen_b64)} bytes", flush=True)
        if current_persona_id:
            procesar_imagen_facial(client, current_persona_id, imagen_b64)
        buffer.clear()
        current_persona_id = None

def procesar_imagen_facial(client, persona_id, imagen_b64):
    file_name = f"{persona_id}.jpg"
    file_path = os.path.join(PREVIEWS_DIR, file_name)

    try:
        img_bytes = base64.b64decode(imagen_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        img.save(file_path)

        print("🧠 Analizando rostro con DeepFace...", flush=True)
        resultado = DeepFace.represent(img_path=file_path, model_name="ArcFace", enforce_detection=True,detector_backend="retinaface")
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE personas SET encoding_facial = %s WHERE id = %s", (json.dumps(resultado[0]['embedding']), persona_id))
        conn.commit()
        cur.close()
        conn.close()

        print(f"🎉 Rostro OK y guardado para ID {persona_id}", flush=True)
        client.publish("esp32/respuesta/facial", json.dumps({"status": "ok", "file_name": file_name}))

    except ValueError:
        print("❌ DeepFace: No se detectó rostro humano.", flush=True)
        client.publish("esp32/respuesta/facial", json.dumps({"status": "error", "mensaje": "No se detecto rostro"}))
    except Exception as e:
        print(f"❌ Error de Servidor: {e}", flush=True)
        client.publish("esp32/respuesta/facial", json.dumps({"status": "error", "mensaje": str(e)}))

def start_mqtt():
    try:
        print(f"🚀 Intentando conectar MQTT a {BROKER_HOST}:{BROKER_PORT}...", flush=True)
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER_HOST, BROKER_PORT, 60)
        client.loop_start()
        return client
    except Exception as e:
        print(f"❌ ERROR CRÍTICO AL CONECTAR MQTT: {e}", flush=True)
        return None