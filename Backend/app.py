import os
from flask import Flask
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
    init_db()           # crea las tablas si no existen
    start_mqtt()        # inicia el listener MQTT
    app.run(
        host='0.0.0.0', # acepta conexiones de la red local
        port=5000,
        debug=True,
        use_reloader=False
    )