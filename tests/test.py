import paho.mqtt.client as mqtt
import time

# CONFIGURACIÓN - Usa los mismos datos que en tu ESP32
# Si usas el broker de Cloudflare/Trycloudflare, asegúrate de que sea la URL correcta
BROKER = "localhost" 
PUERTO = 1883 # O el puerto que definiste (80 para websockets usualmente en túneles)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Conectado al Broker MQTT")
        # Nos suscribimos a todos los tópicos del flujo de imagen
        client.subscribe("esp32/imagen/start")
        client.subscribe("esp32/imagen/part")
        client.subscribe("esp32/imagen/end")
        client.subscribe("esp32/respuesta/facial")
    else:
        print(f"❌ Error de conexión. Código: {rc}")

def on_message(client, userdata, msg):
    print(f"\n[TÓPICO]: {msg.topic}")
    if msg.topic == "esp32/imagen/part":
        # No imprimimos todo el base64 para no llenar la pantalla, solo el tamaño
        print(f"📦 Recibido trozo de imagen: {len(msg.payload)} bytes")
    else:
        print(f"📝 Mensaje: {msg.payload.decode()}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print(f"Intentando conectar a {BROKER}...")
try:
    client.connect(BROKER, PUERTO, 60)
    client.loop_forever()
except Exception as e:
    print(f"❌ No se pudo conectar: {e}")