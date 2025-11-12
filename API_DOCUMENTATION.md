# 📊 Sistema de Gestión de Turnos y Rostros

Sistema completo de reconocimiento facial con gestión de personas, turnos y horarios.

## 🚀 Características

- ✅ Reconocimiento facial con detección de duplicados
- 👥 Gestión de personas registradas
- 🕐 Sistema de turnos personalizables
- 📋 Asignación de turnos a personas
- 💾 Almacenamiento en CSV (compatible con bases de datos futuras)
- 🌐 API REST completa
- 📡 Comunicación MQTT en tiempo real
- 🎨 Interfaz web de gestión

## 📂 Estructura de Archivos

```
back/
├── app.py                  # Backend principal (MQTT + Flask API)
├── docker-compose.yml      # Orquestación de servicios
├── Dockerfile             # Imagen de Python
├── requirements.txt       # Dependencias Python
├── test_api.html         # Interfaz web de gestión
├── data/                 # Datos CSV
│   ├── personas.csv      # Registro de personas
│   ├── turnos.csv        # Turnos disponibles
│   └── asignaciones.csv  # Asignaciones persona-turno
├── imagenes/             # Fotos de rostros registrados
└── test2/codio/          # Firmware ESP32-CAM
    └── codio.ino
```

## 📊 Formato de CSVs

### personas.csv
```csv
id,nombre,fecha_registro,total_imagenes
1,Juan Perez,2024-01-15 10:30:00,3
2,Maria Garcia,2024-01-16 14:20:00,2
```

### turnos.csv
```csv
id,nombre_turno,hora_inicio,hora_fin,dias_semana
1,Mañana,08:00,16:00,"L,M,X,J,V"
2,Tarde,16:00,00:00,"L,M,X,J,V"
3,Noche,00:00,08:00,"L,M,X,J,V"
```

### asignaciones.csv
```csv
persona_id,turno_id,fecha_asignacion
1,1,2024-01-15 11:00:00
1,2,2024-01-15 11:05:00
2,3,2024-01-16 15:00:00
```

## 🌐 API REST Endpoints

### Base URL
```
http://localhost:5000/api
```

### Endpoints Disponibles

#### 1. **GET /api/personas**
Obtiene todas las personas registradas.

**Respuesta:**
```json
{
  "success": true,
  "total": 2,
  "personas": [
    {
      "id": "1",
      "nombre": "Juan Perez",
      "fecha_registro": "2024-01-15 10:30:00",
      "total_imagenes": "3"
    }
  ]
}
```

#### 2. **GET /api/personas/{persona_id}**
Obtiene detalles de una persona específica incluyendo sus turnos asignados.

**Respuesta:**
```json
{
  "success": true,
  "persona": {
    "id": "1",
    "nombre": "Juan Perez",
    "fecha_registro": "2024-01-15 10:30:00",
    "total_imagenes": "3",
    "turnos": [
      {
        "id": "1",
        "nombre_turno": "Mañana",
        "hora_inicio": "08:00",
        "hora_fin": "16:00",
        "dias_semana": "L,M,X,J,V",
        "fecha_asignacion": "2024-01-15 11:00:00"
      }
    ]
  }
}
```

#### 3. **GET /api/turnos**
Obtiene todos los turnos disponibles.

**Respuesta:**
```json
{
  "success": true,
  "total": 3,
  "turnos": [
    {
      "id": "1",
      "nombre_turno": "Mañana",
      "hora_inicio": "08:00",
      "hora_fin": "16:00",
      "dias_semana": "L,M,X,J,V"
    }
  ]
}
```

#### 4. **POST /api/turnos**
Crea un nuevo turno.

**Request Body:**
```json
{
  "nombre_turno": "Fin de Semana",
  "hora_inicio": "09:00",
  "hora_fin": "18:00",
  "dias_semana": "S,D"
}
```

**Respuesta:**
```json
{
  "success": true,
  "message": "Turno creado exitosamente",
  "turno_id": "4"
}
```

#### 5. **GET /api/asignaciones**
Obtiene todas las asignaciones con información completa.

**Respuesta:**
```json
{
  "success": true,
  "total": 2,
  "asignaciones": [
    {
      "persona": {
        "id": "1",
        "nombre": "Juan Perez",
        "fecha_registro": "2024-01-15 10:30:00",
        "total_imagenes": "3"
      },
      "turno": {
        "id": "1",
        "nombre_turno": "Mañana",
        "hora_inicio": "08:00",
        "hora_fin": "16:00",
        "dias_semana": "L,M,X,J,V"
      },
      "fecha_asignacion": "2024-01-15 11:00:00"
    }
  ]
}
```

#### 6. **POST /api/asignaciones**
Asigna un turno a una persona.

**Request Body:**
```json
{
  "persona_id": "1",
  "turno_id": "2"
}
```

**Respuesta:**
```json
{
  "success": true,
  "message": "Turno asignado exitosamente"
}
```

#### 7. **DELETE /api/asignaciones/{persona_id}/{turno_id}**
Elimina una asignación específica.

**Respuesta:**
```json
{
  "success": true,
  "message": "Asignación eliminada exitosamente"
}
```

#### 8. **GET /api/health**
Verifica el estado del sistema.

**Respuesta:**
```json
{
  "success": true,
  "status": "running",
  "mqtt_connected": true,
  "total_personas": 5,
  "total_turnos": 3
}
```

## 🔧 Instalación y Uso

### 1. Iniciar el sistema con Docker:
```bash
docker-compose up -d --build
```

### 2. Verificar que los servicios estén corriendo:
```bash
docker-compose ps
```

### 3. Ver logs en tiempo real:
```bash
docker-compose logs -f reconocimiento
```

### 4. Acceder a la interfaz web:
Abrir en el navegador: `test_api.html`

### 5. Probar la API:
```bash
# Obtener personas
curl http://localhost:5000/api/personas

# Obtener turnos
curl http://localhost:5000/api/turnos

# Verificar salud del sistema
curl http://localhost:5000/api/health
```

## 📡 Comunicación MQTT

### Topics de Registro:
- `test/registro/{nombre}/start` - Inicio de transmisión de imagen
- `test/registro/{nombre}/part` - Partes de imagen en Base64
- `test/registro/{nombre}/end` - Fin de transmisión

### Topics de Respuesta:
- `test/respuesta/{nombre}` - Respuestas del servidor al ESP32

### Formato de Respuestas MQTT:
```
ESTADO|MENSAJE
```

Ejemplos:
- `REGISTRADO|Juan registrado exitosamente!`
- `DUPLICADO|El rostro de Juan ya esta registrado`
- `ERROR|Este rostro pertenece a Pedro (85%)`

## 🎯 Flujo de Trabajo

1. **Registro de Rostro:**
   - ESP32-CAM captura foto desde interfaz web
   - Envía imagen via MQTT en chunks Base64
   - Backend recibe, detecta rostro con face_recognition
   - Guarda en `imagenes/` y registra en `personas.csv`
   - Envía confirmación via MQTT

2. **Gestión de Turnos:**
   - Acceder a `test_api.html`
   - Ver personas registradas
   - Asignar turnos desde interfaz
   - Datos se guardan en `asignaciones.csv`

3. **Consulta de API:**
   - Usar endpoints REST para integración
   - Obtener datos en formato JSON
   - Compatible con cualquier frontend o sistema externo

## 🔮 Migración a Base de Datos

Los CSVs están diseñados para fácil migración a SQL:

```sql
-- Tabla personas
CREATE TABLE personas (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nombre VARCHAR(255) NOT NULL,
    fecha_registro DATETIME NOT NULL,
    total_imagenes INT DEFAULT 0
);

-- Tabla turnos
CREATE TABLE turnos (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nombre_turno VARCHAR(100) NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    dias_semana VARCHAR(50)
);

-- Tabla asignaciones
CREATE TABLE asignaciones (
    persona_id INT,
    turno_id INT,
    fecha_asignacion DATETIME NOT NULL,
    PRIMARY KEY (persona_id, turno_id),
    FOREIGN KEY (persona_id) REFERENCES personas(id),
    FOREIGN KEY (turno_id) REFERENCES turnos(id)
);
```

## 📱 Puertos Utilizados

- **1883**: MQTT Broker (Mosquitto)
- **5000**: API REST (Flask)
- **80**: ESP32-CAM Web Interface

## 🛠️ Tecnologías

- **Backend**: Python 3.11, Flask, paho-mqtt, face_recognition
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Hardware**: ESP32-CAM (AI Thinker)
- **Broker**: Eclipse Mosquitto
- **Almacenamiento**: CSV (migrable a PostgreSQL/MySQL)
- **Contenedores**: Docker, Docker Compose

## 📝 Notas

- Los archivos CSV se crean automáticamente al iniciar
- Turnos por defecto (Mañana, Tarde, Noche) se crean al inicio
- Las imágenes se guardan con timestamp único
- El sistema previene rostros duplicados automáticamente
- Compatible con futura integración de base de datos

## 🆘 Solución de Problemas

### El API no responde:
```bash
docker-compose restart reconocimiento
```

### Ver logs de errores:
```bash
docker-compose logs reconocimiento | tail -50
```

### Verificar MQTT:
```bash
docker-compose logs mosquitto
```

### Limpiar y reiniciar:
```bash
docker-compose down
docker-compose up -d --build
```
