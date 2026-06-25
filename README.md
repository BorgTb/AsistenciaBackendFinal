# Sistema de Asistencia SAS — Análisis Completo del Sistema

Sistema integral de control de asistencia biométrica con **reconocimiento facial (DeepFace)**, **huella digital**, **dispositivos ESP32-CAM**, **notificaciones email**, **integración ERP** y **gestión multitenant** (múltiples empresas).

---

## Índice

1. [Arquitectura General](#1-arquitectura-general)
2. [Componentes del Sistema](#2-componentes-del-sistema)
3. [Flujo de Registro Biométrico](#3-flujo-de-registro-biométrico)
4. [Flujo de Marcación (Asistencia)](#4-flujo-de-marcación-asistencia)
5. [Seguridad y Cifrado](#5-seguridad-y-cifrado)
6. [Autenticación y Autorización (RBAC)](#6-autenticación-y-autorización-rbac)
7. [Comunicación con Dispositivos (MQTT)](#7-comunicación-con-dispositivos-mqtt)
8. [Base de Datos y Modelo de Datos](#8-base-de-datos-y-modelo-de-datos)
9. [Integración con ERP](#9-integración-con-erp)
10. [Notificaciones Email](#10-notificaciones-email)
11. [Modo Seguro (TLS/HTTPS)](#11-modo-seguro-tlshttps)
12. [Diagrama de Flujo Completo](#12-diagrama-de-flujo-completo)
13. [Infraestructura y Despliegue](#13-infraestructura-y-despliegue)
14. [Stack Tecnológico](#14-stack-tecnológico)
15. [Variables de Entorno](#15-variables-de-entorno)

---

## 1. Arquitectura General

```
                    ┌──────────────────────────────────────────────────┐
                    │                  INTERNET / LAN                   │
                    └──────────────────────────────────────────────────┘
                              │              │              │
                    ┌─────────┘              │              └──────────┐
                    ▼                        ▼                        ▼
           ┌────────────────┐    ┌────────────────────┐    ┌──────────────────┐
           │   Navegador     │    │  ESP32-CAM (N)    │    │   ERP Externo     │
           │  (Next.js SPA)  │    │  (Dispositivos)   │    │   (Webhook)       │
           │    :3000        │    │   :1884/8884      │    │                   │
           └───────┬────────┘    └─────────┬──────────┘    └────────┬─────────┘
                   │ HTTP/WS               │ MQTT                   │ HTTP POST
                   ▼                       ▼                        │
           ┌─────────────────────────────────────────────────────────┐│
           │                    ┌──────────────┐                     ││
           │                    │   Mosquitto   │◄────────────────────┘│
           │                    │  (MQTT MQTT)  │                     │
           │                    └──────┬───────┘                     │
           │                           │                             │
           │                           ▼                             │
           │  ┌──────────────────────────────────────────────┐      │
           │  │              Backend Flask                   │      │
           │  │  ┌──────────┐  ┌──────────┐  ┌───────────┐  │      │
           │  │  │   API    │  │   MQTT   │  │ Facial    │  │      │
           │  │  │  REST    │  │  Handler │  │ (DeepFace)│  │      │
           │  │  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │      │
           │  │       │              │              │         │      │
           │  │  ┌────▼─────────────▼──────────────▼─────┐   │      │
           │  │  │         PostgreSQL (15)               │   │      │
           │  │  └──────────────────────────────────────┘   │      │
           │  └──────────────────────────────────────────────┘      │
           └─────────────────────────────────────────────────────────┘
```

El sistema se compone de **4 capas principales**:

| Capa | Tecnología | Rol |
|---|---|---|
| **Frontend** | Next.js (TypeScript, React) | Interfaz de usuario web, paneles, reportes |
| **Backend API** | Flask (Python) | Lógica de negocio, REST API, autenticación |
| **Broker MQTT** | Eclipse Mosquitto | Comunicación bidireccional con dispositivos ESP32 |
| **Base de Datos** | PostgreSQL 15 | Persistencia de toda la información |

---

## 2. Componentes del Sistema

### 2.1 Backend — Flask (`Backend/`)

```
Backend/
├── app.py                    # Punto de entrada, SSE, CORS, init
├── database.py               # Conexión PostgreSQL, init_db (migraciones)
├── encryption.py             # Cifrado Fernet para embeddings faciales
├── mqtt_handler.py           # Cliente MQTT, heartbeat, watchdog
├── eventos_mqtt.py           # Notificación MQTT de cambios (sincronización)
├── routes/
│   ├── auth.py               # Login, JWT, RBAC, enrolamiento dispositivos
│   ├── personas.py           # CRUD personas + consentimiento biométrico + eliminación de datos
│   ├── turnos.py             # CRUD turnos
│   ├── asignaciones.py       # Asignación persona ↔ turno
│   ├── asistencias.py        # Marcaciones, sync, detección duplicados
│   ├── facial.py             # Registro/verificación/identificación facial
│   ├── dispositivos.py       # CRUD dispositivos, comandos remotos
│   ├── logs.py               # Logs de sincronización
│   └── erp.py                # Integración webhook con ERP externo
├── services/
│   └── email_service.py      # Notificaciones SMTP
├── certs/                    # Certificados TLS (producción)
├── mosquitto/                # Config Mosquitto + contraseñas
└── tests/                    # Tests unitarios e integración
```

### 2.2 Frontend — Next.js (`Frontend/`)

```
Frontend/
├── app/                      # App Router (Next.js 14)
│   ├── api/_proxy.ts         # Proxy de API para evitar CORS
│   └── ...                   # Páginas (login, dashboard, etc.)
├── components/               # Componentes React
│   └── SasDashboard.tsx      # Dashboard principal con websocket
├── lib/
│   └── useDeviceWebSocket.ts # WebSocket para estado dispositivos
├── middleware.ts             # Middleware Next.js (protección rutas)
└── playwright.config.ts      # Tests E2E
```

---

## 3. Flujo de Registro Biométrico

### 3.1 Registro Facial

```
Persona ──► Frontend ──► POST /api/facial/registrar ──► Backend
                                      │
                                      ├── ¿Consentimiento biométrico?
                                      │   ├── NO  → 403 Forbidden
                                      │   └── SÍ  → continúa
                                      │
                                      ├── Guardar imagen JPG en static/previews/
                                      ├── Validar calidad (varianza Laplacian ≥ umbral)
                                      │   ├── FALLO → 400 Bad Request + log
                                      │   └── OK   → continúa
                                      │
                                      ├── Extraer embedding con DeepFace (FaceNet)
                                      ├── Detectar duplicados (distancia euclidiana)
                                      │   ├── DUPLICADO → 409 Conflict
                                      │   └── ÚNICO → continúa
                                      │
                                      ├── Cifrar embedding con Fernet (AES-256)
                                      ├── Guardar en encodings_faciales + personas
                                      └── Log biométrico (auditoría)
```

**Rutas involucradas:**
- `POST /api/facial/registrar` — registro desde web
- `POST /api/facial/agregar-foto` — agregar foto adicional a persona
- `PUT /api/facial/actualizar/<id>` — reemplazar rostro
- `esp32/imagen/registrar` (MQTT) — registro desde dispositivo ESP32

### 3.2 Registro de Huella

```
Admin ──► POST /api/dispositivos/<id>/registrar-huella
              │
              ├── Verificar propiedad del dispositivo (empresa_id)
              ├── Publicar MQTT: backend/huella/registrar/{mac}
              │
Dispositivo ◄── (MQTT) recibe comando, captura huella
              │
              ├── Publica resultado: esp32/huella/resultado/{mac}
              │
Backend ─────► Procesa resultado:
              ├── Actualiza personas.huella_id
              ├── Notifica sincronización a otros dispositivos
              └── SSE broadcast a frontend
```

---

## 4. Flujo de Marcación (Asistencia)

### 4.1 Identificación Facial (método principal)

```
ESP32-CAM ──► HTTP POST /api/facial/identificar (JPEG raw o JSON+Base64)
                      │
                      ├── Guardar captura en static/capturas_prueba/
                      ├── Validar calidad de imagen (anti-spoofing)
                      │   └── FALLO → log + error
                      │
                      ├── Extraer embedding con DeepFace (anti_spoofing=True)
                      ├── Comparar contra BD (embeddings cacheados con TTL)
                      │   ├── Cache hit → usar embeddings en memoria
                      │   └── Cache miss → recargar desde BD (cada 60s)
                      │
                      ├── Best match < umbral_distancia (10.0)?
                      │   ├── SÍ → persona identificada
                      │   └── NO → "Rostro no reconocido"
                      │
                      └── Log biométrico de identificación
```

### 4.2 Registro de Asistencia

```
Identificación exitosa ──► POST /api/asistencias (o sync)
                                    │
                                    ├── Detección de duplicados (misma persona + tipo + día)
                                    │   └── DUPLICADO → retorna id existente (idempotente)
                                    │
                                    ├── Insertar en asistencias (persona_id, tipo, método, turno_id)
                                    ├── Disparar ERP push async (webhook)
                                    ├── Disparar notificación email async (opcional)
                                    └── Retornar id de asistencia
```

**Métodos de marcación** (`metodo`):
- `huella` — huella digital en dispositivo
- `facial` — reconocimiento facial
- `manual` — marcación manual en web
- `test` — pruebas

---

## 5. Seguridad y Cifrado

### 5.1 Cifrado de Embeddings Facial (Fernet / AES-256)

```python
# encryption.py
BIOMETRIC_KEY = os.getenv("BIOMETRIC_KEY")

def _derivar_fernet_key() -> bytes:
    digest = hashlib.sha256(BIOMETRIC_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

_fernet = Fernet(_derivar_fernet_key())

def cifrar_embedding(embedding: list) -> str:
    plano = json.dumps(embedding).encode("utf-8")
    cifrado = _fernet.encrypt(plano)
    return base64.urlsafe_b64encode(cifrado).decode("ascii")
```

| Aspecto | Detalle |
|---|---|
| Algoritmo | **Fernet** (AES-128-CBC + HMAC-SHA256) |
| Clave | Derivada vía **SHA-256** de `BIOMETRIC_KEY` |
| Input | Embedding facial (vector de 128 floats de FaceNet) |
| Output | Base64 URL-safe del token Fernet |
| Seguridad | Los embeddings almacenados en BD **no son legibles** sin la clave |

### 5.2 Cifrado de Contraseñas (bcrypt)

```python
# auth.py
pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
# Verificación:
bcrypt.checkpw(password.encode('utf-8'), pw_hash.encode('utf-8'))
```

### 5.3 JWT (JSON Web Tokens)

| Parámetro | Valor |
|---|---|
| Algoritmo | HS256 |
| Secreto | `JWT_SECRET` (via env) |
| Expiración | 24 horas (`JWT_EXP_HOURS`) |
| Payload | `user_id`, `empresa_id`, `rol`, `persona_id`, `exp` |

### 5.4 Protección Anti-Spoofing

```python
# facial.py
embedding = extraer_embedding(file_path, anti_spoofing=True)

def extraer_embedding(img_path, anti_spoofing=False):
    resultado = DeepFace.represent(
        img_path=img_path,
        model_name="Facenet",
        enforce_detection=True,
        detector_backend=DETECTOR_BACKEND,
        anti_spoofing=anti_spoofing  # ← Detecta fotos/videos falsos
    )
```

### 5.5 Validación de Calidad de Imagen

```python
# facial.py
def _validar_calidad_imagen(img_path):
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    varianza = cv2.Laplacian(img, cv2.CV_64F).var()
    if varianza < UMBRAL_NITIDEZ:
        return False, "Imagen con baja nitidez, posible spoof o captura borrosa"
```

### 5.6 Auditoría Biométrica

Toda operación biométrica se registra en `logs_biometricos`:

```sql
CREATE TABLE logs_biometricos (
    id SERIAL PRIMARY KEY,
    persona_id INTEGER,
    dispositivo_id INTEGER,
    timestamp TIMESTAMP DEFAULT NOW(),
    tipo_operacion VARCHAR(30),  -- 'registro', 'verificacion', 'identificacion'
    resultado VARCHAR(20),       -- 'exito', 'fallo', 'no_encontrado', 'duplicado'
    ip_origen VARCHAR(45)        -- IP del cliente
);
```

Las eliminaciones de datos biométricos se registran en `eliminaciones_biometricas`:
- Almacena el embedding anterior (cifrado) por si se requiere deshacer
- Registra qué usuario solicitó la eliminación

### 5.7 Eliminación de Personas (Limpieza de Datos)

El sistema ofrece dos modalidades de eliminación según el rol:

| Rol | Comportamiento | Efecto |
|---|---|---|
| **admin** | `DELETE /api/personas/<id>` | Limpia todos los datos de la persona (rut=NULL, email=NULL, huella_id=NULL), elimina datos biométricos (encodings faciales, consentimientos, foto preview), registra auditoría en `eliminaciones_biometricas` y marca `activo=false`. El registro en `personas` se conserva con su **nombre** para mantener la integridad de las asistencias históricas. |
| **empleador** | `DELETE /api/personas/<id>` | Solo marca `activo=false` (soft delete). La persona no aparece en listados pero sus datos persisten. |
| **admin/trabajador** | `DELETE /api/personas/<id>/datos-biometricos` | Elimina solo los datos biométricos (huella, encodings faciales, consentimiento, foto), más `rut` y `email`. La persona sigue activa. |

Las personas eliminadas (con `activo=false`) no aparecen en los listados del frontend (todos los roles filtran por `activo=true`). Si se registra una persona nueva posteriormente, se crea un registro completamente nuevo sin relación con el anterior.

---

## 6. Autenticación y Autorización (RBAC)

### 6.1 Roles del Sistema

| Rol | Nivel | Permisos |
|---|---|---|
| `admin` | Global | CRUD todas las empresas, usuarios, dispositivos |
| `empleador` | Por empresa | CRUD de su empresa, ver asistencias, gestionar personas |
| `trabajador` | Por empresa | Ver sus propias asistencias, perfil |

### 6.2 Decoradores de Autorización

```python
@token_required              # Requiere JWT válido
@requiere_rol('admin')      # JWT + rol específico
@token_opcional              # JWT opcional, fallback a X-Device-MAC
```

### 6.3 Resolución de Empresa (Multitenant)

El sistema soporta **múltiples empresas** con aislamiento de datos:

1. **Admin** ve todas las empresas
2. **Empleador** solo ve datos de su empresa (filtro por `empresa_id`)
3. **Trabajador** solo ve sus propios datos (filtro por `persona_id`)
4. **Dispositivos** se asocian a una empresa mediante enrolamiento
5. **Fallback** para dispositivos sin JWT: cabecera `X-Device-MAC` resuelve empresa

### 6.4 Enrolamiento de Dispositivos

```
1. Admin/Empleador genera PIN: POST /api/auth/dispositivos/generar-pin
2. Dispositivo se conecta con PIN: POST /api/auth/dispositivos/enrolar
3. Backend asigna MAC + IP, marca como enrolado
4. Dispositivo queda vinculado a la empresa
```

### 6.5 Jerarquía de Creación de Usuarios

```
admin     → puede crear: empleador, trabajador
empleador → puede crear: empleador, trabajador
trabajador → no puede crear usuarios
```

Nadie puede crear un `admin` (solo existe el seed inicial).

---

## 7. Comunicación con Dispositivos (MQTT)

### 7.1 Tópicos MQTT

| Tópico | Dirección | Propósito |
|---|---|---|
| `esp32/imagen/#` | ESP32 → Backend | Imágenes faciales (registro + marcación) |
| `esp32/imagen/registrar` | ESP32 → Backend | Registro facial desde dispositivo |
| `esp32/imagen/eco` | Bidireccional | Heartbeat de conexión MQTT |
| `esp32/asistencia/#` | ESP32 → Backend | Marcaciones de asistencia |
| `esp32/heartbeat/#` | ESP32 → Backend | Heartbeat periódico (actualiza estado) |
| `esp32/lwt/#` | ESP32 → Backend | Last Will Testament (desconexión) |
| `esp32/huella/resultado/#` | ESP32 → Backend | Resultado de registro de huella |
| `backend/comando/{mac}/{cmd}` | Backend → ESP32 | Comandos (reiniciar, reconectar WiFi) |
| `backend/huella/registrar/{mac}` | Backend → ESP32 | Solicitar registro de huella |
| `backend/notificacion/{mac}` | Backend → ESP32 | Notificación de cambios (personas, turnos) |
| `esp32/respuesta/facial` | Backend → ESP32 | Resultado del procesamiento facial |
| `esp32/ping/{mac}` | Backend → ESP32 | Ping para verificar conectividad |

### 7.2 Heartbeat y Watchdog

```
┌──────────────────────────────────────────────────┐
│              Sistema de Heartbeat                 │
├──────────────────────────────────────────────────┤
│                                                   │
│  device_pinger() (cada 30s):                      │
│  ├── Publica esp32/ping/{mac} a cada dispositivo   │
│  └── Marca como 'inactivo' si no responde en 60s  │
│                                                   │
│  device_watchdog() (cada 60s):                    │
│  └── Marca dispositivos sin heartbeat reciente     │
│                                                   │
│  Al iniciar:                                      │
│  └── Todos los dispositivos → 'inactivo'           │
│      (esperando primer heartbeat)                  │
│                                                   │
│  SSE broadcast al frontend en cada cambio:        │
│  └── /sse/devices (Server-Sent Events)             │
└──────────────────────────────────────────────────┘
```

### 7.3 Seguridad MQTT

| Modo | Puerto | Descripción |
|---|---|---|
| No seguro | 1884 (host) / 1883 (container) | MQTT plano, desarrollo local |
| Seguro (TLS) | 8884 (host) / 8883 (container) | MQTT + TLS, producción |
| WebSocket | 9001 | Para clientes web MQTT |

En modo seguro:
- `tls_set(ca_certs=MQTT_SSL_CA)` — certificado CA
- `username_pw_set(MQTT_USER, MQTT_PASSWORD)` — autenticación
- Certificados en `Backend/certs/`

---

## 8. Base de Datos y Modelo de Datos

### 8.1 Esquema Relacional

```sql
empresas (id, nombre, rut_empresa, email_contacto, ...)
    │
    ├── usuarios_web (id, nombre, email, password_hash, activo)
    │       └── usuario_empresa (usuario_id, empresa_id, rol)
    │
    ├── personas (id, empresa_id, nombre, rut [nullable], email, huella_id, encoding_facial, activo)
    │       ├── consentimientos (persona_id, fecha_aceptacion, version_politica, ...)
    │       ├── encodings_faciales (id, persona_id, encoding, foto_path, quality_score)
    │       ├── eliminaciones_biometricas (id, persona_id, embedding_anterior, ...)
    │       ├── logs_biometricos (id, persona_id, tipo_operacion, resultado, ...)
    │       ├── asistencias (id, persona_id, tipo, metodo, fecha_hora, ...)
    │       └── asignaciones (persona_id, turno_id, vigente)
    │
    ├── turnos (id, empresa_id, nombre, hora_inicio, hora_fin, dias, ...)
    │
    ├── dispositivos (id, empresa_id, nombre, mac_address, ip_local, estado, ...)
    │       └── sincronizacion_log (dispositivo_id, registros_enviados, ...)
    │
    └── integraciones_erp (id, empresa_id, webhook_url, headers, field_map, ...)
```

### 8.2 Tablas Clave

| Tabla | Propósito | Registros críticos |
|---|---|---|
| `personas` | Empleados | `encoding_facial` (cifrado), `huella_id`, `rut` nullable (se limpia al eliminar) |
| `encodings_faciales` | Embeddings faciales históricos | Múltiples por persona, con quality_score |
| `consentimientos` | Consentimiento biométrico | Requerido antes de registrar datos |
| `eliminaciones_biometricas` | Auditoría de eliminaciones | Backup del embedding anterior, registro de eliminaciones completas |
| `logs_biometricos` | Auditoría completa | Todo intento de identificación/registro |
| `asistencias` | Marcaciones | Con detección de duplicados por día |
| `dispositivos` | ESP32-CAM | MAC, IP, estado online/offline, contraseña |
| `integraciones_erp` | Webhooks externos | URL, headers, field mapping |

### 8.3 Índices

```sql
-- Personas
CREATE INDEX idx_personas_empresa ON personas(empresa_id);
CREATE INDEX idx_personas_rut ON personas(rut);

-- Facial
CREATE INDEX idx_ef_persona ON encodings_faciales(persona_id);
CREATE INDEX idx_consentimientos_persona ON consentimientos(persona_id);

-- Auditoría
CREATE INDEX idx_logs_biometricos_persona ON logs_biometricos(persona_id);
CREATE INDEX idx_logs_biometricos_timestamp ON logs_biometricos(timestamp);
CREATE INDEX idx_eliminaciones_biometricas_persona ON eliminaciones_biometricas(persona_id);

-- Asistencias
CREATE INDEX idx_asistencias_persona ON asistencias(persona_id);
CREATE INDEX idx_asistencias_dispositivo ON asistencias(dispositivo_id);
CREATE INDEX idx_asistencias_fecha ON asistencias(fecha_hora);

-- ERP
CREATE INDEX idx_erp_activo ON integraciones_erp(activo);
```

---

## 9. Integración con ERP

### 9.1 Arquitectura

```
Marcación ──► POST /api/asistencias
                     │
                     ├── Disparo asíncrono (thread)
                     │
                     └── enviar_asistencia_a_erps()
                             │
                             ├── Consulta integraciones_erp activas
                             │   (misma empresa_id)
                             │
                             └── Por cada ERP configurado:
                                     ├── Transformar datos según field_map
                                     ├── POST HTTP al webhook_url
                                     └── Guardar estado del envío
```

### 9.2 Field Mapping

```json
{
  "rut": "employee_id",
  "nombre": "full_name",
  "tipo": "check_type",
  "fecha_hora": "timestamp"
}
```

Permite adaptar el payload al formato que espera cada ERP sin cambiar código.

### 9.3 Control de Envíos

- `envio_auto`: envía automáticamente cada marcación
- `POST /api/erp/<id>/enviar`: envío manual (batch de últimas 200 asistencias)
- `POST /api/erp/<id>/test`: prueba con datos ficticios
- `GET /api/erp/<id>/estado`: consultar estado del último envío

---

## 10. Notificaciones Email

### 10.1 Configuración SMTP

```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu-correo@gmail.com
SMTP_PASSWORD=tu-password-app
SMTP_USE_TLS=true
MAIL_FROM=no-reply@sas.cl
```

### 10.2 Flujo

```
Marcación exitosa ──► ¿persona.email existe?
                           │
                           ├── SÍ → enviar_notificacion_marcacion()
                           │        ├── Construir email HTML+texto
                           │        ├── Conexión SMTP (STARTTLS o SSL)
                           │        └── Enviar
                           │
                           └── NO → fin
```

### 10.3 Controles

- `DISABLE_ASYNC_DISPATCH=1` deshabilita envíos asíncronos (ERP + email)
- Los envíos fallidos no bloquean la marcación (try/except)
- Timeout de conexión SMTP estándar (depende de smtplib)

---

## 11. Modo Seguro (TLS/HTTPS)

### 11.1 Activación

```bash
SECURE_MODE=true     # Habilita HTTPS + MQTT TLS
```

### 11.2 Efectos al activar

| Componente | Sin TLS | Con TLS |
|---|---|---|
| Flask | HTTP :5000 | HTTP :5000 + HTTPS :443 |
| MQTT | Puerto 1883, plano | Puerto 8883, TLS con CA |
| Certificados | No se usan | `SSL_CERT_PATH`, `SSL_KEY_PATH`, `MQTT_SSL_CA` |
| Autenticación MQTT | No requerida | `MQTT_USER` + `MQTT_PASSWORD` |

### 11.3 Certificados Requeridos

```
Backend/certs/
├── ca.crt          # CA del broker MQTT (solo TLS)
├── server.crt      # Certificado del servidor Flask (solo HTTPS)
└── server.key      # Clave privada del servidor
```

---

## 12. Diagrama de Flujo Completo

### 12.1 Registro de Persona + Facial

```
Admin ──► POST /api/personas
               │
               ├── Crear persona en BD (empresa_id, nombre, rut, email)
               ├── Opcional: registrar consentimiento
               └── Notificar sincronización MQTT

Admin ──► POST /api/facial/registrar
               │
               ├── Verificar consentimiento
               ├── Validar calidad imagen
               ├── Extraer embedding (DeepFace)
               ├── Detectar duplicados
               ├── Cifrar embedding (Fernet)
               ├── Guardar en encodings_faciales + personas
               └── Log biométrico
```

### 12.2 Marcación Completa (desde ESP32)

```
ESP32 ──► Captura foto + envía a POST /api/facial/identificar
               │
               ├── Guardar captura en disco (auditoría)
               ├── Validar calidad (Laplacian)
               ├── Extraer embedding (DeepFace + anti-spoofing)
               ├── Buscar match en BD (embeddings cacheados)
               │   └── No match → "Rostro no reconocido"
               │
               └── Match exitoso:
                     │
                     ├── Log biométrico (identificación exitosa)
                     ├── Crear asistencia (POST /api/asistencias)
                     │       ├── Detectar duplicado (misma persona/tipo/día)
                     │       ├── Guardar en BD
                     │       └── Disparar push ERP (async)
                     │
                     └── [Opcional] Enviar email notificación (async)
```

### 12.3 Sincronización de Datos a Dispositivos

```
Cambio en BD (persona/turno/asignación)
       │
       └── notificar_sincronizacion(empresa_id, tipo, accion, id)
               │
               ├── Consultar dispositivos enrolados de la empresa
               ├── Publicar MQTT: backend/notificacion/{mac}
               │   payload: {tipo, accion, id, timestamp}
               │
               └── Dispositivos reciben y solicitan datos actualizados
```

---

## 13. Infraestructura y Despliegue

### 13.1 Docker Compose

```yaml
Servicios:
  postgres:     # PostgreSQL 15 con health check
  mosquitto:    # Eclipse Mosquitto con TLS y WebSocket
  backend:      # Flask + DeepFace + MQTT
  frontend:     # Next.js (SSR)
Volúmenes:
  - postgres_data       # Persistencia BD
  - mosquitto_data      # Persistencia Mosquitto
  - mosquitto_log       # Logs Mosquitto
  - backend_static      # Imágenes de capturas/previews
  - deepface_models     # Modelos de FaceNet (~500MB)
Red:
  - teleasist_network   # Bridge interna
```

### 13.2 Puertos Expuestos

| Puerto Host | Servicio | Uso |
|---|---|---|
| 3000 | Frontend | Web UI |
| 5000 | Backend | API Flask |
| 443 | Backend | API Flask HTTPS (solo modo seguro) |
| 5432 | PostgreSQL | Base de datos (solo interno) |
| 1884 | Mosquitto | MQTT plano (mapeado a 1883) |
| 8884 | Mosquitto | MQTT TLS (mapeado a 8883) |
| 9001 | Mosquitto | MQTT WebSocket |

### 13.3 Despliegue en Producción

```bash
# 1. Configurar variables seguras
export JWT_SECRET="$(openssl rand -base64 32)"
export POSTGRES_PASSWORD="$(openssl rand -base64 16)"
export BIOMETRIC_KEY="$(openssl rand -base64 32)"

# 2. Generar certificados TLS
./Backend/certs/generate.sh   # Script de generación autofirmados

# 3. Iniciar en modo seguro
SECURE_MODE=true docker compose up -d

# 4. Verificar
docker compose ps
docker compose logs -f
```

---

## 14. Stack Tecnológico

### Backend (Python)

| Dependencia | Uso |
|---|---|
| Flask | Framework web REST |
| Flask-CORS | Cross-Origin Resource Sharing |
| psycopg2 | Conexión PostgreSQL |
| paho-mqtt | Cliente MQTT |
| deepface | Reconocimiento facial (FaceNet) |
| opencv-python | Procesamiento de imágenes, validación calidad |
| numpy | Álgebra lineal (distancias euclidianas) |
| cryptography | Fernet (cifrado AES de embeddings) |
| PyJWT | JSON Web Tokens |
| bcrypt | Hash de contraseñas |
| Pillow | Manipulación de imágenes |
| gunicorn | Servidor WSGI (producción) |

### Frontend (TypeScript/React)

| Dependencia | Uso |
|---|---|
| Next.js 14 | Framework React SSR |
| React | UI components |
| Tailwind CSS | Estilos |
| Vitest | Tests unitarios |
| Playwright | Tests E2E |

### Infraestructura

| Componente | Propósito |
|---|---|
| Docker | Contenedores |
| Docker Compose | Orquestación |
| PostgreSQL 15 | Base de datos relacional |
| Eclipse Mosquitto | Broker MQTT |
| FaceNet (DeepFace) | Modelo de embeddings faciales |
| MTCNN / RetinaFace | Detectores faciales |

---

## 15. Variables de Entorno

Todas las variables documentadas en `.env.example`:

```
# PostgreSQL
POSTGRES_USER            # Usuario BD (default: sas)
POSTGRES_PASSWORD        # Contraseña BD (default: sas123)
POSTGRES_DB              # Nombre BD (default: sas_db)

# Flask Backend
DATABASE_URL             # URL completa PostgreSQL
JWT_SECRET               # Clave secreta JWT (¡CAMBIAR EN PRODUCCIÓN!)
BIOMETRIC_KEY            # Clave para cifrar embeddings (¡CAMBIAR EN PRODUCCIÓN!)

# Reconocimiento Facial
FACIAL_DETECTOR          # mtcnn | retinaface | ssd | opencv
FACIAL_NITIDEZ_UMBRAL    # Varianza Laplacian mínima (default: 50)
FACIAL_UMBRAL_DISTANCIA  # Distancia euclidiana máxima para match (default: 10.0)
FACIAL_CACHE_TTL         # TTL de caché de embeddings en segundos (default: 60)

# Modo Seguro
SECURE_MODE              # false=desarrollo, true=producción con TLS
MQTT_SSL_PORT            # Puerto MQTT TLS (default: 8883)
MQTT_SSL_CA              # Ruta CA certificado
MQTT_USER                # Usuario MQTT (default: sas)
MQTT_PASSWORD            # Contraseña MQTT
SSL_CERT_PATH            # Ruta certificado HTTPS
SSL_KEY_PATH             # Ruta clave privada HTTPS

# MQTT (no seguro)
MQTT_HOST                # Host del broker (default: mosquitto)
MQTT_PORT                # Puerto MQTT plano (default: 1883)

# SMTP (notificaciones email)
SMTP_SERVER              # Servidor SMTP
SMTP_PORT                # Puerto SMTP (default: 587)
SMTP_USER                # Usuario SMTP
SMTP_PASSWORD            # Contraseña SMTP
SMTP_USE_TLS             # Usar STARTTLS (default: true)
MAIL_FROM                # Dirección remitente

# Frontend
FLASK_API_BASE_URL       # URL del backend para SSR
NEXT_PUBLIC_API_BASE_URL # URL pública del backend
NEXT_PUBLIC_API_URL      # URL API para el frontend
NEXT_PUBLIC_DEVICE_BASE_URL  # URL base para dispositivos (default: http://192.168.4.1)

# Debug / Desarrollo
DISABLE_ASYNC_DISPATCH   # 1 para deshabilitar envíos async (ERP + email)
```

---

## Resumen de Seguridad

| Aspecto | Implementación |
|---|---|
| **Cifrado en reposo** | Embeddings faciales cifrados con Fernet (AES-128-CBC + HMAC) |
| **Cifrado en tránsito** | HTTPS (Flask) + TLS (MQTT) en modo seguro |
| **Hash de contraseñas** | bcrypt (salting automático) |
| **Autenticación API** | JWT (HS256, expiración 24h) |
| **Autorización** | RBAC con 3 roles (admin, empleador, trabajador) |
| **Aislamiento multitenant** | Filtro por empresa_id en todas las consultas |
| **Anti-spoofing facial** | DeepFace + validación de nitidez (Laplacian) |
| **Auditoría biométrica** | logs_biometricos + eliminaciones_biometricas |
| **Consentimiento biométrico** | Tabla consentimientos, requerido antes del registro |
| **Heartbeat dispositivos** | Watchdog cada 60s, timeout 60s, detección de caídas |
| **LWT (Last Will)** | Detección inmediata de desconexión MQTT |
| **Enrolamiento seguro** | PIN temporal de 8 caracteres para vincular dispositivos |
| **Contraseña dispositivos** | SHA-256 de contraseña de 12 caracteres (opcional) |
| **SSE en tiempo real** | Server-Sent Events para broadcast de cambios |
| **Detección de duplicados** | Misma persona + tipo + día → idempotente |
| **Control de acceso a datos** | Personas/turnos/asistencias filtrados por empresa, rol y `activo=true` |
