# test_backend_mqtt.py — poner en la misma carpeta que mqtt_handler.py
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from mqtt_handler import start_mqtt
import time

print("Iniciando start_mqtt()...")
client = start_mqtt()

if client is None:
    print("❌ start_mqtt() retorno None — fallo al conectar")
else:
    print(f"✅ Cliente creado: {client}")
    print("Esperando 3 segundos para ver logs de conexion...")
    time.sleep(3)
    print(f"   ¿Conectado?: {client.is_connected()}")