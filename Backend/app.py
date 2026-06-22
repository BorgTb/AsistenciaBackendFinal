import os
import json
import queue
import threading
from collections import deque
from flask import Flask, Response, stream_with_context
from flask_cors import CORS
from database import init_db
from routes.personas import personas_bp
from routes.turnos import turnos_bp
from routes.asignaciones import asignaciones_bp
from routes.asistencias import asistencias_bp
from routes.facial import facial_bp
from routes.dispositivos import dispositivos_bp
from routes.logs import logs_bp
from routes.erp import erp_bp
from routes.auth import auth_bp
from mqtt_handler import start_mqtt


app = Flask(__name__)
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'sas-secret-cambiar-en-produccion')
CORS(app)

# SSE device stream globals
device_clients = []
clients_lock = threading.Lock()
recent_events = deque(maxlen=100)

def broadcast_device_update(data: dict):
    with clients_lock:
        for q in device_clients:
            try:
                q.put_nowait(data)
            except queue.Full:
                pass
    recent_events.append(data)

@app.route('/sse/devices')
def device_stream():
    def generate():
        q = queue.Queue(maxsize=50)
        with clients_lock:
            for event in recent_events:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass
            device_clients.append(q)
        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            with clients_lock:
                if q in device_clients:
                    device_clients.remove(q)
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    return response

# Registrar rutas
app.register_blueprint(auth_bp)
app.register_blueprint(personas_bp)
app.register_blueprint(turnos_bp)
app.register_blueprint(asignaciones_bp)
app.register_blueprint(asistencias_bp)
app.register_blueprint(facial_bp)
app.register_blueprint(dispositivos_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(erp_bp)

# Ruta de salud para verificar que el backend está vivo
@app.route('/health')
def health():
    return {'status': 'ok', 'version': '1.0'}

if __name__ == '__main__':
    print("¡¡¡NUEVO CÓDIGO CARGADO!!!")
    init_db()
    mqtt_client = start_mqtt(broadcast_device_update)
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False,
        threaded=True
    )