import paho.mqtt.client as mqtt
import base64
import json

buffer = []
BROKER_HOST = "localhost"
BROKER_PORT = 1883

def on_connect(client, userdata, flags, rc):
    print(f"MQTT conectado: {rc}")
    client.subscribe("esp32/imagen/#")
    client.subscribe("esp32/asistencia/#")

def on_message(client, userdata, msg):
    global buffer
    topic = msg.topic.split("/")[-1]

    if topic == "start":
        buffer.clear()
    elif topic == "part":
        buffer.append(msg.payload.decode())
    elif topic == "end":
        imagen_b64 = "".join(buffer)
        # aquí puedes guardar la imagen o procesarla
        print(f"Imagen recibida, tamaño base64: {len(imagen_b64)}")
        buffer.clear()

def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()
    return client