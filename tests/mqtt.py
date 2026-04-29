# test_mqtt.py
import paho.mqtt.client as mqtt
import time

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
RESULTADOS = {}

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Conectado al broker ({BROKER_HOST}:{BROKER_PORT})", flush=True)
        client.subscribe("#")
        print("📡 Suscrito a todos los topicos (#)", flush=True)
    else:
        print(f"❌ Fallo conexion. Codigo rc={rc}", flush=True)
        RESULTADOS["conexion"] = False

def on_message(client, userdata, msg):
    print(f"📩 Mensaje recibido | Topico: {msg.topic} | Payload: {msg.payload.decode()}", flush=True)
    RESULTADOS["mensaje_recibido"] = True

def on_subscribe(client, userdata, mid, granted_qos):
    print(f"📋 Suscripcion confirmada (mid={mid}, qos={granted_qos})", flush=True)
    RESULTADOS["suscrito"] = True

    # Publicar DESPUES de confirmar suscripcion
    time.sleep(0.3)
    print("📢 Publicando mensaje de prueba...", flush=True)
    client.publish("test/ping", "hola desde python")

client = mqtt.Client(client_id="test-diagnostico", clean_session=True)
client.on_connect  = on_connect
client.on_message  = on_message
client.on_subscribe = on_subscribe

print(f"🔌 Conectando a {BROKER_HOST}:{BROKER_PORT}...", flush=True)
try:
    client.connect(BROKER_HOST, BROKER_PORT, 60)
except Exception as e:
    print(f"❌ No se pudo conectar: {e}", flush=True)
    exit(1)

client.loop_start()
time.sleep(3)
client.loop_stop()

# Reporte final
print("\n── RESULTADO ──────────────────────")
print(f"  Conexion:          {'✅' if RESULTADOS.get("conexion") != False else '❌'}")
print(f"  Suscripcion OK:    {'✅' if RESULTADOS.get("suscrito") else '❌'}")
print(f"  Mensaje recibido:  {'✅' if RESULTADOS.get("mensaje_recibido") else '❌'}")
print("───────────────────────────────────")

if not RESULTADOS.get("mensaje_recibido"):
    print("\n⚠️  El broker no retorno el mensaje.")
    print("   → Verifica que mosquitto.conf tenga 'allow_anonymous true'")
    print("   → Verifica que el listener no este restringido a 127.0.0.1")