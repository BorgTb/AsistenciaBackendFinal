from flask import Flask
from flask_cors import CORS
from database import init_db
from routes.personas import personas_bp
from routes.turnos import turnos_bp
from routes.asignaciones import asignaciones_bp
from routes.asistencias import asistencias_bp
from routes.facial import facial_bp
from mqtt_handler import start_mqtt


app = Flask(__name__)
CORS(app)  # permite conexiones desde el ESP32

# Registrar rutas
app.register_blueprint(personas_bp)
app.register_blueprint(turnos_bp)
app.register_blueprint(asignaciones_bp)
app.register_blueprint(asistencias_bp)
app.register_blueprint(facial_bp)

# Ruta de salud para verificar que el backend está vivo
@app.route('/health')
def health():
    return {'status': 'ok', 'version': '1.0'}

if __name__ == '__main__':
    init_db()           # crea las tablas si no existen
    start_mqtt()        # inicia el listener MQTT
    app.run(
        host='0.0.0.0', # acepta conexiones de la red local
        port=5000,
        debug=True,
        use_reloader=False
    )