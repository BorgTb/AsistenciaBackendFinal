import paho.mqtt.client as mqtt
import json
import os
import time
import threading
from datetime import datetime, timezone
from database import get_connection, resolver_rut_a_id

BROKER_HOST = os.getenv('MQTT_HOST', '127.0.0.1')
BROKER_PORT = int(os.getenv('MQTT_PORT', '1884'))

SECURE_MODE = os.getenv('SECURE_MODE', 'false').lower() == 'true'
MQTT_TLS_PORT = int(os.getenv('MQTT_SSL_PORT', '8883'))
MQTT_SSL_CA = os.getenv('MQTT_SSL_CA', 'certs/ca.crt')
MQTT_USER = os.getenv('MQTT_USER', 'sas')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')

heartbeat_times = {}
heartbeat_lock = threading.Lock()

PREVIEWS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static', 'previews'))
os.makedirs(PREVIEWS_DIR, exist_ok=True)

def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print(f"❌ MQTT fallo conexion. Codigo: {rc}", flush=True)
        return

    print(f"🟢 MQTT conectado (rc={rc})", flush=True)
    client.subscribe("esp32/imagen/#")
    client.subscribe("esp32/asistencia/#")
    client.subscribe("esp32/heartbeat/#")
    client.subscribe("esp32/lwt/#")
    client.subscribe("esp32/huella/resultado/#")
    print("📡 Suscripciones registradas.", flush=True)

    # FIX: publicar el eco en un hilo separado con delay
    # para darle tiempo al loop de procesar la suscripcion
    def eco_delayed():
        time.sleep(0.5)
        client.publish("esp32/imagen/eco", "Python esta vivo")
        print("📢 Eco enviado.", flush=True)

    threading.Thread(target=eco_delayed, daemon=True).start()

def on_message(client, userdata, msg):
    # Extraer el tópico completo de forma segura
    full_topic = str(msg.topic)
    
    # Imprimir CUALQUIER COSA que llegue para depuración
    print(f"📩 [MQTT] Recibido en: {full_topic} | Tamaño: {len(msg.payload)} bytes", flush=True)

    if full_topic == "esp32/imagen/eco":
        print("✅ ECO OK — Python se escucha a si mismo.", flush=True)
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
                    "UPDATE dispositivos SET ultimo_heartbeat = NOW(), estado = 'activo', ip_local = %s WHERE REPLACE(mac_address, ':', '') = %s RETURNING id, nombre, ip_local, estado, ultimo_heartbeat",
                    (ip, mac)
                )
            else:
                cur.execute(
                    "UPDATE dispositivos SET ultimo_heartbeat = NOW(), estado = 'activo' WHERE REPLACE(mac_address, ':', '') = %s RETURNING id, nombre, ip_local, estado, ultimo_heartbeat",
                    (mac,)
                )
            row = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            if row:
                broadcast_device_update({
                    'id': str(row[0]),
                    'nombre': row[1],
                    'ip': row[2] or '',
                    'estado': 'activo',
                    'ultimo_heartbeat': str(row[4]) if row[4] else None,
                    'online': True
                })
        except Exception as e:
            print(f"❌ Error heartbeat DB: {e}", flush=True)
        return

    if full_topic.startswith("esp32/asistencia/"):
        mac = full_topic.split("/")[-1]
        try:
            payload = json.loads(msg.payload.decode())
            rut = payload.get('rut')
            tipo = payload.get('tipo', payload.get('check_type'))
            metodo = payload.get('metodo', 'huella')
            timestamp = payload.get('fecha_hora', payload.get('datetime'))

            conn = get_connection()
            cur = conn.cursor()

            if not rut and payload.get('persona_id'):
                cur.execute("SELECT rut FROM personas WHERE id = %s", (payload['persona_id'],))
                row = cur.fetchone()
                rut = row[0] if row else None

            persona_id = None
            nombre = payload.get('nombre', '')
            if rut:
                persona_id = resolver_rut_a_id(rut)
                if not persona_id:
                    cur.execute(
                        "INSERT INTO personas (empresa_id, nombre, rut, activo) VALUES (1, %s, %s, TRUE) RETURNING id",
                        (nombre or rut, rut)
                    )
                    persona_id = cur.fetchone()[0]
                    conn.commit()
                    print(f"🆕 Persona creada desde ESP32: {rut}", flush=True)

            if persona_id and tipo:
            # Detect duplicate: same persona + same type + same day
                cur.execute(
                    "SELECT id FROM asistencias WHERE persona_id = %s AND tipo = %s AND DATE(fecha_hora) = CURRENT_DATE",
                    (persona_id, tipo)
                )
                if cur.fetchone():
                    print(f"⏭️ Asistencia duplicada ignorada: persona {persona_id} / {tipo}", flush=True)
                    cur.close()
                    conn.close()
                    return

                cur.execute(
                    "SELECT empresa_id, nombre FROM personas WHERE id = %s", (persona_id,)
                )
                p_row = cur.fetchone()
                empresa_id = p_row[0] if p_row else None
                if not nombre:
                    nombre = p_row[1] if p_row else ''

                from routes.asistencias import fecha_hora_forzada
                # La fecha de demo, si esta definida, manda por sobre la del ESP32.
                timestamp = fecha_hora_forzada() or timestamp
                if timestamp:
                    cur.execute(
                        "INSERT INTO asistencias (persona_id, nombre, tipo, metodo, fecha_hora, origen, sincronizado) VALUES (%s, %s, %s, %s, %s, 'dispositivo', TRUE) RETURNING id, fecha_hora",
                        (persona_id, nombre, tipo, metodo, timestamp)
                    )
                else:
                    cur.execute(
                        "INSERT INTO asistencias (persona_id, nombre, tipo, metodo, origen, sincronizado) VALUES (%s, %s, %s, %s, 'dispositivo', TRUE) RETURNING id, fecha_hora",
                        (persona_id, nombre, tipo, metodo)
                    )
                row_i = cur.fetchone()
                asist_id = row_i[0]
                fec_hora = row_i[1]
                conn.commit()
                print(f"✅ Asistencia ESP32 registrada: {nombre} / {tipo} (ID {asist_id})", flush=True)
                cur.close()
                conn.close()

                # Trigger ERP push
                from routes.asistencias import _disparar_erp_push
                if empresa_id:
                    _disparar_erp_push(persona_id, nombre, tipo, metodo, fec_hora, empresa_id)
            else:
                cur.close()
                conn.close()
                print(f"⚠️ ESP32 asistencia ignorada: faltan datos {payload}", flush=True)
        except Exception as e:
            print(f"❌ Error procesando asistencia ESP32: {e}", flush=True)
        return

    if full_topic.startswith("esp32/lwt/"):
        mac = full_topic.split("/")[-1]
        print(f"⚠️ LWT recibido: dispositivo {mac} desconectado", flush=True)
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE dispositivos SET estado = 'inactivo' WHERE REPLACE(mac_address, ':', '') = %s RETURNING id, nombre, ip_local, estado",
                (mac,)
            )
            row = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            if row:
                broadcast_device_update({
                    'id': str(row[0]),
                    'nombre': row[1],
                    'ip': row[2] or '',
                    'estado': 'inactivo',
                    'ultimo_heartbeat': None,
                    'online': False
                })
                print(f"📡 Broadcast WebSocket: {row[1]} desconectado", flush=True)
        except Exception as e:
            print(f"❌ Error LWT DB: {e}", flush=True)
        return

    if full_topic.startswith("esp32/huella/resultado"):
        try:
            payload = json.loads(msg.payload.decode())
            persona_id = payload.get("persona_id")
            huella_id = payload.get("huella_id")
            status = payload.get("status")

            if status == "ok" and persona_id and huella_id:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("UPDATE personas SET huella_id = %s WHERE id = %s", (huella_id, persona_id))
                conn.commit()
                cur.execute("SELECT empresa_id FROM personas WHERE id = %s", (persona_id,))
                row = cur.fetchone()
                empresa_id = row[0] if row else None
                cur.close()
                conn.close()

                if empresa_id:
                    from eventos_mqtt import notificar_sincronizacion
                    notificar_sincronizacion(empresa_id, 'personas', 'actualizar', int(persona_id))

                if _huella_broadcast_callback:
                    try:
                        _huella_broadcast_callback({
                            "persona_id": str(persona_id),
                            "huella_id": huella_id,
                            "status": "ok"
                        })
                    except Exception as e:
                        print(f"⚠️ Error broadcasting huella SSE: {e}", flush=True)

                print(f"✅ Huella {huella_id} registrada para persona {persona_id}", flush=True)
            else:
                print(f"⚠️ Resultado huella error/no ok: {payload}", flush=True)
        except Exception as e:
            print(f"❌ Error procesando resultado huella: {e}", flush=True)
        return

_broadcast_callback = None
_huella_broadcast_callback = None
_mqtt_client = None

def broadcast_device_update(data: dict):
    try:
        if _broadcast_callback:
            _broadcast_callback(data)
    except Exception as e:
        print(f"⚠️ Error broadcasting SSE: {e}", flush=True)

def enviar_comando_dispositivo(mac: str, comando: str) -> bool:
    if _mqtt_client is None:
        print(f"❌ MQTT no disponible para enviar comando {comando} a {mac}", flush=True)
        return False
    topic = f"backend/comando/{mac}/{comando}"
    _mqtt_client.publish(topic, json.dumps({"comando": comando}))
    print(f"📤 Comando enviado: {topic}", flush=True)
    return True


def device_pinger():
    while True:
        time.sleep(30)
        if _mqtt_client is None:
            continue
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT REPLACE(mac_address, ':', '') as mac FROM dispositivos WHERE enrolado = TRUE AND mac_address IS NOT NULL AND mac_address != ''"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            ahora = time.time()
            with heartbeat_lock:
                for (mac,) in rows:
                    topic = f"esp32/ping/{mac}"
                    _mqtt_client.publish(topic, f"{{\"t\":{ahora}}}")
                    if mac not in heartbeat_times:
                        heartbeat_times[mac] = 0
                vencidos = [mac for mac, t in heartbeat_times.items() if t > 0 and (ahora - t) > HEARTBEAT_TIMEOUT]
            for mac in vencidos:
                try:
                    conn2 = get_connection()
                    cur2 = conn2.cursor()
                    cur2.execute(
                        "UPDATE dispositivos SET estado = 'inactivo' WHERE REPLACE(mac_address, ':', '') = %s RETURNING id, nombre, ip_local, estado",
                        (mac,)
                    )
                    row = cur2.fetchone()
                    conn2.commit()
                    cur2.close()
                    conn2.close()
                    if row:
                        broadcast_device_update({
                            'id': str(row[0]),
                            'nombre': row[1],
                            'ip': row[2] or '',
                            'estado': 'inactivo',
                            'ultimo_heartbeat': None,
                            'online': False
                        })
                        print(f"⏱ Pinger: dispositivo {row[1]} sin respuesta, marcado inactivo", flush=True)
                except Exception as e:
                    print(f"❌ Error pinger DB: {e}", flush=True)
        except Exception as e:
            print(f"❌ Error pinger: {e}", flush=True)

def start_mqtt(broadcast_callback=None, huella_broadcast_callback=None):
    global _broadcast_callback, _huella_broadcast_callback, _mqtt_client
    try:
        if SECURE_MODE:
            port = MQTT_TLS_PORT
            print(f"🔒 Modo SEGURO: conectando MQTT con TLS a {BROKER_HOST}:{port}...", flush=True)
            client = mqtt.Client(client_id="python-backend", clean_session=True)
            client.tls_set(ca_certs=MQTT_SSL_CA)
            client.tls_insecure_set(True)
            if MQTT_PASSWORD:
                client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        else:
            port = BROKER_PORT
            print(f"🔓 Modo NO SEGURO: conectando MQTT a {BROKER_HOST}:{port}...", flush=True)
            client = mqtt.Client(client_id="python-backend", clean_session=True)
            if MQTT_PASSWORD:
                client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER_HOST, port, 60)
        client.loop_start()
        _mqtt_client = client
        if broadcast_callback:
            _broadcast_callback = broadcast_callback
            print("🔌 SSE broadcast vinculado", flush=True)
        if huella_broadcast_callback:
            _huella_broadcast_callback = huella_broadcast_callback
            print("🔌 SSE huella broadcast vinculado", flush=True)
        threading.Thread(target=device_watchdog, daemon=True).start()
        threading.Thread(target=device_pinger, daemon=True).start()
        print("📡 Pinger MQTT activo (ping cada 30s)", flush=True)
        return client
    except Exception as e:
        print(f"❌ ERROR CRITICO MQTT: {e}", flush=True)
        return None

HEARTBEAT_TIMEOUT = 60

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
                    "UPDATE dispositivos SET estado = 'inactivo' WHERE REPLACE(mac_address, ':', '') = %s RETURNING id, nombre, ip_local, estado",
                    (mac,)
                )
                row = cur.fetchone()
                conn.commit()
                cur.close()
                conn.close()
                if row:
                    broadcast_device_update({
                        'id': str(row[0]),
                        'nombre': row[1],
                        'ip': row[2] or '',
                        'estado': 'inactivo',
                        'ultimo_heartbeat': None,
                        'online': False
                    })
            except Exception as e:
                print(f"❌ Error watchdog DB: {e}", flush=True)