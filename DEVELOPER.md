# Documentación Técnica - Sistema de Asistencia (SAS)

Guía para que cualquier desarrollador pueda levantar, entender y extender el sistema.

## 1. Arquitectura general

El sistema tiene 4 componentes que se comunican entre sí:

```
┌─────────────┐      MQTT       ┌──────────────┐      HTTP/REST     ┌──────────────┐
│  ESP32-CAM  │ ◄─────────────► │   Mosquitto  │ ◄─────────────────►│   Backend    │
│ (firmware)  │                 │   (broker)   │                    │  (Flask)     │
└─────────────┘                 └──────────────┘                    └──────┬───────┘
                                                                            │ SQL
                                                            HTTP/REST + SSE │
                                                                            ▼
                                  ┌──────────────┐                  ┌──────────────┐
                                  │   Frontend   │ ◄────────────────│  PostgreSQL  │
                                  │  (Next.js)   │                  └──────────────┘
                                  └──────────────┘
```

- **Backend** (`Backend/`): API REST en Flask, lógica de negocio, reconocimiento facial (DeepFace), cifrado biométrico, cliente MQTT y streaming SSE hacia el frontend.
- **Frontend** (`Frontend/`): aplicación Next.js 16 / React 19 que consume la API REST y se suscribe a los streams SSE.
- **esp32-cam** (`esp32-cam/`): firmware del dispositivo (cámara/lector de huella) que publica/suscribe eventos MQTT.
- **Infraestructura** (`docker-compose.yml`): PostgreSQL + Mosquitto (broker MQTT) + Backend + Frontend, todo orquestado con Docker Compose.

## 2. Requisitos previos

- Docker y Docker Compose (recomendado para levantar todo de una vez).
- Alternativamente, para desarrollo local sin Docker: Python 3.12, Node.js 20+, PostgreSQL 15, un broker MQTT (Mosquitto).

## 3. Levantar el entorno completo (Docker Compose)

```bash
docker-compose up --build
```

Esto levanta:
- `postgres` → puerto `5432`
- `mosquitto` → puertos `1884` (MQTT plano), `8884` (MQTT TLS), `9001` (WebSocket)
- `backend` → puertos `5000` (HTTP) y `443` (HTTPS si `SECURE_MODE=true`)
- `frontend` → puerto `3000`

Variables configurables vía `.env` en la raíz (ver sección 6): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, `JWT_SECRET`, `MQTT_PASSWORD`, `SECURE_MODE`.

## 4. Backend (Flask)

Ubicación: `Backend/`. Punto de entrada: `Backend/app.py`.

### 4.1 Ejecución local sin Docker

```bash
cd Backend
pip install -r requirements.txt
python app.py
```

El arranque (`app.py`):
1. Inicializa la base de datos (`database.init_db()`), creando tablas e índices si no existen, y sembrando una empresa y un usuario admin por defecto (`admin@empresa.cl` / `admin123` — **cambiar en producción**).
2. Registra los blueprints de `Backend/routes/`.
3. Inicia el cliente MQTT (`mqtt_handler.start_mqtt()`).
4. Sirve la API en el puerto `5000` (o `443` con TLS si `SECURE_MODE=true`, usando `SSL_CERT_PATH`/`SSL_KEY_PATH`).
5. Expone endpoints SSE (`/sse/devices`, `/sse/huellas`) que reenvían en tiempo real eventos llegados por MQTT al frontend.

### 4.2 Estructura de rutas (`Backend/routes/`)

Todas las rutas (salvo login) requieren JWT vía `Authorization: Bearer <token>`, validado por el decorador `@token_required` en `routes/auth.py`. `@requiere_rol(*roles)` restringe por rol (`admin`, `empleador`, `trabajador`). `@token_opcional` permite acceso sin token (usado por endpoints que también aceptan autenticación por MAC del dispositivo).

| Blueprint | Archivo | Endpoints principales |
|---|---|---|
| `auth_bp` | `routes/auth.py` | `/api/auth/login`, `/register`, `/usuarios`, `/empresas`, `/change-password`, `/me`, `/solicitar-eliminacion-datos`, `/dispositivos/generar-pin`, `/dispositivos/enrolar` |
| `personas_bp` | `routes/personas.py` | `/api/personas`, `/<id>`, `/duplicados`, `/merge`, `/<id>/biometrico`, `/<id>/huella`, `/<id>/consentimiento`, `/<id>/datos-biometricos` |
| `turnos_bp` | `routes/turnos.py` | `/api/turnos`, `/<id>` (CRUD de turnos) |
| `asignaciones_bp` | `routes/asignaciones.py` | `/api/asignaciones`, `/<id>` (asignación turno-persona) |
| `asistencias_bp` | `routes/asistencias.py` | `/api/asistencias`, `/sync`, `/device-sync`, `/device`, `/<id>` |
| `facial_bp` | `routes/facial.py` | `/api/facial/registrar`, `/agregar-foto`, `/actualizar/<id>`, `/verificar`, `/identificar`, `/identificar-o-registrar` |
| `dispositivos_bp` | `routes/dispositivos.py` | `/api/dispositivos`, `/<id>`, `/<id>/reasignar`, `/verificar`, `/<id>/generar-password` |
| `logs_bp` | `routes/logs.py` | `/api/logs` |
| `erp_bp` | `routes/erp.py` | `/api/erp`, `/<id>`, `/<id>/test`, `/<id>/enviar`, `/<id>/estado` |

### 4.3 Reconocimiento facial y cifrado biométrico

- `routes/facial.py` usa **DeepFace** para generar embeddings faciales a partir de fotos.
- `Backend/encryption.py` cifra cada embedding con **Fernet (AES-128)** antes de guardarlo en `encodings_faciales.encoding`. La clave se deriva con SHA-256 de la variable de entorno `BIOMETRIC_KEY`. Incluye fallback de lectura en texto plano para compatibilidad con datos antiguos.
- Las huellas digitales se enrolan en el dispositivo ESP32; el backend solo recibe el resultado vía MQTT.

### 4.4 MQTT (`Backend/mqtt_handler.py`, `Backend/eventos_mqtt.py`)

Tópicos que el backend **suscribe**:
- `esp32/asistencia/<mac>` — marca de asistencia (`rut`, `tipo`, `metodo`, `fecha_hora`, `nombre`, `persona_id`); resuelve la persona por RUT, inserta en `asistencias` y dispara sincronización con ERP. Deduplica marcas del mismo tipo/persona en el mismo día.
- `esp32/heartbeat/<mac>` — estado de salud del dispositivo (IP, estado); actualiza `dispositivos` y reenvía por SSE.
- `esp32/lwt/<mac>` — Last Will Testament MQTT; marca el dispositivo como `inactivo` si se desconecta abruptamente.
- `esp32/huella/resultado/<mac>` — resultado de enrolamiento de huella; actualiza `personas.huella_id` y reenvía por SSE.

Tópicos que el backend **publica**:
- `backend/notificacion/<mac>` — notifica al dispositivo cambios de sincronización (turnos, asignaciones, personas).
- `esp32/imagen/eco` — eco de salud al conectar.

### 4.5 Servicios auxiliares (`Backend/services/`)

- `email_service.py`: envío de correos SMTP para notificación de marcaciones y para el flujo de solicitudes de eliminación de datos biométricos (cumplimiento tipo GDPR). Configurado vía `SMTP_*` / `MAIL_FROM`.

### 4.6 Base de datos (`Backend/database.py`)

- Conexión vía `psycopg2` usando `DATABASE_URL` (formato `postgresql://user:pass@host:puerto/db`).
- `init_db()` crea automáticamente todas las tablas e índices si no existen: `empresas`, `usuarios_web`, `usuario_empresa`, `personas`, `turnos`, `asignaciones`, `asistencias`, `encodings_faciales`, `logs_biometricos`, `eliminaciones_biometricas`, `consentimientos`, `solicitudes_eliminacion`, `dispositivos`, `sincronizacion_log`, `integraciones_erp`, `duplicados_pendientes`.

### 4.7 Tests del backend

```bash
cd Backend
pip install -r requirements-test.txt
docker-compose -f tests/docker-compose.test.yml up -d   # Postgres de pruebas en :5433
pytest tests/
pytest tests/ --cov=.
```

`tests/conftest.py` apunta `DATABASE_URL` a la base de pruebas y mockea DeepFace/OpenCV para no descargar modelos ML en cada corrida.

## 5. Frontend (Next.js)

Ubicación: `Frontend/`. Stack: Next.js 16, React 19, TypeScript.

```bash
cd Frontend
npm install
npm run dev          # http://localhost:3000
```

Variable clave: `FLASK_API_BASE_URL` (apunta al backend, por defecto `http://backend:5000` en Docker o `http://localhost:5000` en local).

Scripts disponibles (`package.json`):
- `npm run build` / `npm run start` — build y ejecución de producción.
- `npm run lint` — linting.
- `npm test` / `npm run test:watch` / `npm run test:coverage` — tests unitarios con Vitest.
- `npm run test:e2e` — tests end-to-end con Playwright.

## 6. Variables de entorno

Archivo `.env` en `Backend/` (no existe `.env.example`; crear uno propio basado en esta lista):

| Variable | Descripción | Default |
|---|---|---|
| `DATABASE_URL` | Cadena de conexión PostgreSQL | — (requerida) |
| `JWT_SECRET` | Clave de firma de JWT | `sas-secret-cambiar-en-produccion` |
| `BIOMETRIC_KEY` | Clave de cifrado de embeddings faciales | `cambia-esta-clave-biometrica-en-produccion` |
| `SECURE_MODE` | Activa HTTPS en el backend | `false` |
| `SSL_CERT_PATH` / `SSL_KEY_PATH` | Rutas a certificado/clave TLS | — |
| `MQTT_HOST` / `MQTT_PORT` | Host y puerto del broker MQTT | `127.0.0.1` / `1884` |
| `MQTT_USER` / `MQTT_PASSWORD` | Credenciales MQTT | `sas` / `sas123` |
| `SMTP_SERVER` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `MAIL_FROM` / `SMTP_USE_TLS` | Configuración de envío de correo | — |

**Importante:** cambiar `JWT_SECRET`, `BIOMETRIC_KEY` y las credenciales del usuario admin por defecto (`admin@empresa.cl` / `admin123`) antes de desplegar a producción.

## 7. Flujo típico de marcación de asistencia (extremo a extremo)

1. El ESP32-CAM captura una imagen o lectura de huella y publica en `esp32/asistencia/<mac>` vía MQTT.
2. `mqtt_handler.py` recibe el mensaje, resuelve la persona por RUT, inserta el registro en `asistencias` y deduplica marcas repetidas del mismo día.
3. Se dispara sincronización opcional con un ERP configurado (`erp_bp`).
4. El frontend, suscrito a `/sse/devices`, recibe la actualización en tiempo real sin hacer polling.
5. Para enrolamiento facial: el frontend sube fotos a `/api/facial/registrar`; DeepFace genera el embedding, que se cifra (`encryption.py`) antes de guardarse.

## 8. Convenciones de seguridad a respetar

- Nunca loguear ni exponer embeddings faciales sin cifrar.
- Toda ruta nueva en `Backend/routes/` debe usar `@token_required` o `@requiere_rol(...)`, salvo que exista una razón explícita para acceso público/dispositivo (`@token_opcional`).
- Los secretos (`JWT_SECRET`, `BIOMETRIC_KEY`, credenciales MQTT/SMTP) se inyectan siempre por variable de entorno, nunca hardcodeados en código nuevo.
