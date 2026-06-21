# Arquitectura del Sistema de Asistencia IoT (SAS)

Documento de referencia arquitectónica que describe los tres componentes del sistema: **ESP32-CAM** (firmware), **Backend Flask** (API + lógica de negocio) y **Frontend Next.js** (panel de administración).

> Versión del documento: 1.0 · Stack: Next.js 16 + React 19, Flask + psycopg2, ESP32-CAM (Arduino), PostgreSQL 15, Mosquitto MQTT, Docker Compose.

---

## 1. Visión general

El sistema es una **plataforma de control de asistencia con biometría (facial + huella)** pensada para operar con hardware IoT de bajo costo en terreno y un backend central en la nube.

```
┌──────────────────┐        ┌────────────────────┐        ┌──────────────────┐
│  Navegador Web   │  HTTP  │   Frontend Next.js │  HTTP  │   Backend Flask  │
│  (Panel admin)   │◄──────►│  (proxy REST)      │◄──────►│  + DeepFace      │
└──────────────────┘   :3000└────────────────────┘  :5000  └──────────────────┘
                                                                      │  ▲
                                              psycopg2                │  │  MQTT
                                                                      ▼  │  (1883/WS)
                                                  ┌──────────────────┐   │
                                                  │  PostgreSQL 15   │   │
                                                  │  (Neon o local)  │   │
                                                  └──────────────────┘   │
                                                                         │
                          WiFi / AP ◄─────► ┌──────────────────┐        │
                          192.168.4.1       │    ESP32-CAM     │        │
                          (LittleFS/SPIFFS) │   (Arduino)      │◄───────┘
                                           └──────────────────┘
```

### Componentes

| Componente | Ubicación | Función |
|---|---|---|
| **Backend Flask** | `Backend/` | API REST, biometría (DeepFace), MQTT broker client, lógica de negocio, persistencia |
| **Frontend Next.js** | `Frontend/` | Panel de administración con App Router, dashboard, formularios, llamadas proxy |
| **ESP32-CAM** | `esp32-cam/` | Firmware Arduino: cámara, sensor de huella (AS608), servidor web local, cliente MQTT, cliente HTTP |
| **PostgreSQL** | docker / Neon | Persistencia de personas, turnos, asignaciones, asistencias, logs, ERP, consentimientos |
| **Mosquitto** | docker | Broker MQTT (puerto interno 1883, mapeado a 1884) |
| **Docker Compose** | raíz | Levanta los 4 servicios en red `teleasist_net` |

---

## 2. Backend (Flask + Python)

### 2.1 Stack y dependencias

Archivo: `Backend/requirements.txt`

```
flask
psycopg2-binary
python-dotenv
deepface
numpy
pillow
flask-cors
paho-mqtt
requests
bcrypt
PyJWT
cryptography      ← añadido para cifrado AES de embeddings biométricos
```

| Capa | Tecnología |
|---|---|
| Web framework | Flask 3 (blueprints) |
| DB driver | psycopg2-binary (consultas SQL crudas, sin ORM) |
| Variables de entorno | python-dotenv |
| Biometría | DeepFace + TensorFlow (modelo `Facenet`, detector `retinaface`) |
| MQTT | paho-mqtt (cliente embebido) |
| Hashing | bcrypt para contraseñas |
| Auth | PyJWT (HS256) |
| Cifrado | cryptography (Fernet = AES-128-CBC + HMAC) |

### 2.2 Estructura de carpetas

```
Backend/
├── app.py                      # Entry point Flask + arranque MQTT
├── database.py                 # Conexión psycopg2 + init_db() (crea/evoluciona esquema)
├── encryption.py               # ⭐ Cifrado AES de embeddings biométricos
├── mqtt_handler.py             # Cliente MQTT: recepción de imágenes del ESP32
├── tests/                       # Tests automatizados (pytest, 284 tests, 90% cobertura)
├── requirements.txt
├── Dockerfile
├── .env                        # DATABASE_URL real (Neon en producción)
├── DB/
│   ├── schema.sql              # DDL de referencia (no ejecutado automáticamente)
│   └── migracion_usuario_empresa.sql
├── mosquitto/                  # Volumen del broker
├── static/
│   ├── previews/               # Fotos de enrolamiento {persona_id}.jpg
│   └── capturas_prueba/        # Capturas de debugging de identificación
└── routes/
    ├── auth.py                 # Login, registro, JWT, decoradores
    ├── personas.py             # CRUD personas + huella + datos biométricos
    ├── turnos.py               # CRUD turnos
    ├── asignaciones.py         # CRUD asignaciones persona↔turno
    ├── asistencias.py          # Marcajes + sync desde dispositivos
    ├── facial.py               # ⭐ Registro, verificación, identificación facial
    ├── dispositivos.py         # Listar, ping, enrolar dispositivos
    ├── erp.py                  # Webhooks a ERPs (Odoo, Buk, SAP, etc.)
    └── logs.py                 # Logs de sincronización
```

### 2.3 Modelado de datos (PostgreSQL)

10 tablas + 3 tablas de seguridad añadidas recientemente:

#### Núcleo
| Tabla | Propósito | Campos clave |
|---|---|---|
| `empresas` | Empresas (multi-tenant) | `id`, `nombre`, `rut_empresa`, `email_contacto` |
| `dispositivos` | Dispositivos ESP32 enrolados | `id`, `empresa_id`, `mac_address`, `ip_local`, `estado`, `ultimo_heartbeat`, `codigo_enrol`, `enrolado` |
| `usuarios_web` | Usuarios del panel web | `id`, `nombre`, `email`, `password_hash`, `activo` |
| `usuario_empresa` | M:N usuario↔empresa con rol | `usuario_id`, `empresa_id`, `rol` (admin/empleador/trabajador) |
| `personas` | Personas registradas | `id`, `empresa_id`, `nombre`, `rut` UNIQUE, `email`, **`huella_id`** (1-127), **`encoding_facial`** TEXT (cifrado), `activo` |
| `turnos` | Turnos de trabajo | `id`, `empresa_id`, `nombre`, `hora_inicio`, `hora_fin`, `dias`, `activo` |
| `asignaciones` | Asignación persona↔turno | `persona_id`, `turno_id`, `vigente` |
| `asistencias` | Marcajes de asistencia | `id`, `persona_id`, `dispositivo_id`, `nombre`, `tipo` (entrada/salida), `metodo`, `fecha_hora`, `origen`, `sincronizado` |
| `sincronizacion_log` | Logs de sync desde dispositivo | `dispositivo_id`, `registros_enviados`, `registros_ok`, `estado`, `detalle` |
| `integraciones_erp` | Webhooks a ERPs externos | `empresa_id`, `nombre`, `tipo`, `webhook_url`, `headers`, `field_map`, `envio_auto`, `activo`, `ultimo_envio` |

#### Seguridad y cumplimiento (Seguridad.md)
| Tabla | Propósito |
|---|---|
| `consentimientos` | Registro de consentimiento biométrico por persona |
| `logs_biometricos` | Auditoría de toda operación biométrica (registro, verificación, identificación, eliminación) |
| `eliminaciones_biometricas` | Trazabilidad del derecho al olvido (quién solicitó, cuándo, embedding previo) |

### 2.4 Inicialización y migraciones

**No hay Alembic ni migraciones versionadas.** La estrategia es:

- `database.py::init_db()` se llama al iniciar `app.py`. Usa `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para evolucionar el esquema.
- Scripts SQL sueltos en `Backend/DB/` para migraciones puntuales.
- Seed inicial: empresa `id=1` "Empresa por defecto" + usuario admin (`admin@empresa.cl` / `admin123`).

### 2.5 Autenticación y autorización

- **JWT HS256** con secreto de `JWT_SECRET`.
- Token expira en 24 h (`JWT_EXP_HOURS`).
- Carga útil (payload): `user_id`, `empresa_id`, `rol`, opcional `persona_id`, `exp`.
- **Decoradores disponibles** (`Backend/routes/auth.py`):
  - `@token_required` — exige Authorization Bearer
  - `@requiere_rol(*roles)` — combina `token_required` + chequeo de rol
  - `@token_opcional` — lee token si existe, también acepta `X-Device-MAC` (para llamadas internas del ESP32)
  - `@solo_mis_datos` — fuerza persona_id del token en `kwargs`

### 2.6 Endpoints REST

> **Patrón**: todos los endpoints cuelgan de `app.register_blueprint(...)` en `app.py`. Prefijo: `/api/...`

#### Autenticación (`routes/auth.py` · `auth_bp`)
| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/api/auth/login` | – | Login. Si el usuario tiene 1 sola empresa → token; si tiene varias → `need_empresa` |
| POST | `/api/auth/register` | admin/empleador | Crear usuario. Empleador solo puede crear `trabajador` |
| GET  | `/api/auth/me` | token | Perfil propio |
| PUT  | `/api/auth/change-password` | token | Cambiar contraseña |
| GET  | `/api/auth/usuarios` | admin/empleador | Listar usuarios |
| DELETE | `/api/auth/usuarios/<id>` | admin/empleador | Quitar usuario de empresa |
| GET  | `/api/auth/empresas` | admin | Listar empresas |
| POST | `/api/auth/empresas` | admin | Crear empresa |
| DELETE | `/api/auth/empresas/<id>` | admin | Eliminar empresa |
| POST | `/api/auth/asignar-usuario` | admin | Asignar usuario a empresa con rol |

#### Personas (`routes/personas.py` · `personas_bp`)
| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/personas` | opcional | Listar (filtrado por rol/empresa) |
| POST | `/api/personas` | opcional | Crear persona |
| PUT/PATCH | `/api/personas/<id>` | opcional | Actualizar nombre/email |
| DELETE | `/api/personas/<id>` | opcional | Admin: hard delete; empleador: soft (`activo=false`) |
| PUT | `/api/personas/<id>/huella` | opcional | Asignar `huella_id` (1-127) |
| POST | `/api/personas/<id>/consentimiento` | opcional | ⭐ Registrar consentimiento biométrico |
| DELETE | `/api/personas/<id>/datos-biometricos` | opcional | ⭐ Derecho al olvido: borra embedding + foto + huella + consentimiento (conservando asistencias) |

#### Turnos y asignaciones
- `routes/turnos.py` (`turnos_bp`): GET/POST `/api/turnos`, DELETE `/api/turnos/<id>`
- `routes/asignaciones.py` (`asignaciones_bp`): GET/POST `/api/asignaciones`, DELETE `/api/asignaciones/<id>`

#### Asistencias (`routes/asistencias.py` · `asistencias_bp`)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/asistencias` | Listar (filtrado por rol). 500 últimas admin/empleador, 200 últimas por persona |
| POST | `/api/asistencias` | Marcar asistencia. Tras commit, dispara push asíncrono a ERPs |
| POST | `/api/asistencias/sync` | Bulk sync desde dispositivo. Detecta duplicados (60 s ventana) |

#### Facial (`routes/facial.py` · `facial_bp`) ⭐ componente crítico
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/facial/registrar` | **Verifica consentimiento** → extrae embedding Facenet → detecta duplicados (umbral 10) → **cifra embedding** → guarda → log |
| PUT | `/api/facial/actualizar/<id>` | Reemplaza el embedding facial |
| POST | `/api/facial/verificar` | 1:1 — descifra embedding almacenado y compara con captura |
| POST | `/api/facial/identificar` | 1:N — recibe JPEG crudo (octet-stream) o Base64, busca el match más cercano |

Modelo: **Facenet** + detector **retinaface** + opcional **anti-spoofing** (en verificar/identificar).

#### Dispositivos (`routes/dispositivos.py` + parte de `auth.py`)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/dispositivos` | Listar dispositivos de la empresa |
| PUT | `/api/dispositivos/<id>` | Renombrar |
| DELETE | `/api/dispositivos/<id>` | Eliminar |
| POST | `/api/dispositivos/verificar` | Ping HTTP a la IP del ESP32 (`GET /estado`) |
| POST | `/api/auth/dispositivos/generar-pin` | Genera PIN de enrolamiento (8 chars) |
| POST | `/api/dispositivos/enrolar` | ESP32 envía `{codigo, mac, ip}` → activa el dispositivo |

#### ERP (`routes/erp.py` · `erp_bp`)
| Método | Ruta | Descripción |
|---|---|---|
| GET/POST | `/api/erp` | Listar/crear integraciones |
| DELETE | `/api/erp/<id>` | Eliminar |
| POST | `/api/erp/<id>/test` | Enviar payload de prueba |
| POST | `/api/erp/<id>/enviar` | Reenviar últimas 200 asistencias |
| GET | `/api/erp/<id>/estado` | Última hora + status |
| GET | `/api/dispositivos/erp-config` | Config que el ESP32 descarga para push directo |

Presets soportados: **generic, odoo, defontana, buk, sap**.

### 2.7 Cifrado biométrico (`Backend/encryption.py`)

- AES simétrico mediante **Fernet** (AES-128-CBC + HMAC-SHA256).
- La clave `BIOMETRIC_KEY` (env var) se deriva con SHA-256 → base64 url-safe → Fernet key.
- `cifrar_embedding(embedding_list)` → `str` (base64 urlsafe del Fernet ciphertext).
- `descifrar_embedding(texto)` → lista. **Tiene fallback**: si la desencriptación falla, intenta `json.loads()` para mantener compatibilidad con embeddings antiguos sin cifrar.
- Se aplica en: `routes/facial.py` (registro, actualizar, verificar, identificar) y `mqtt_handler.py`.

### 2.8 Cliente MQTT embebido (`Backend/mqtt_handler.py`)

El backend se conecta al broker Mosquitto como **cliente** (no publica, solo recibe).

- **Tópico de suscripción**: `esp32/imagen/#` (en particular `esp32/imagen/registrar`).
- **Otros tópicos escuchados**:
  - `esp32/heartbeat/<mac>` → actualiza `dispositivos.ultimo_heartbeat` y `estado=activo`
  - `esp32/lwt/<mac>` → marca `estado=inactivo`
  - `esp32/asistencia/#` → informativo
  - `esp32/imagen/eco` → debug
- **Flujo de enrolamiento facial**:
  1. ESP32 publica payload JSON `{persona_id, imagen_b64}` en `esp32/imagen/registrar` (un solo mensaje, no fragmentado en la versión actual).
  2. `procesar_imagen_facial()` valida consentimiento, decodifica, guarda en `static/previews/{persona_id}.jpg`, extrae embedding con DeepFace, **lo cifra** y lo guarda.
  3. Responde en `esp32/respuesta/facial` con `{status, mensaje}` o `{status, file_name}`.
- **Watchdog** (`device_watchdog`): corre cada 60 s, marca `inactivo` a dispositivos sin heartbeat >90 s.
- **Inicialización**: `start_mqtt()` se invoca en `app.py` al arrancar el backend.

### 2.9 Despacho asíncrono a ERPs (`asistencias.py`)

`POST /api/asistencias` y `/api/asistencias/sync` lanzan, tras el commit, un `threading.Thread` daemon con `enviar_asistencia_a_erps(empresa_id)`:
- Lee todas las integraciones activas con `envio_auto=TRUE` de esa empresa.
- Aplica `field_map` JSON para renombrar campos (`persona_id` → `employee_id` etc.).
- POST al `webhook_url` con timeout 10 s.
- Actualiza `integraciones_erp.ultimo_envio` y `ultimo_estado`.

---

## 3. Frontend (Next.js 16 + React 19)

### 3.1 Stack y dependencias

`Frontend/package.json`

```json
{
  "next": "^16.2.6",
  "react": "19.0.0",
  "react-dom": "19.0.0"
}
```

Sin librerías adicionales: **sin Tailwind, sin shadcn, sin librerías de UI**. Estilos en CSS puro (`app/globals.css`). Fuente: `DM Sans` (sans) + `Space Mono` (mono) vía `next/font/google`.

### 3.2 Estructura de carpetas

```
Frontend/
├── package.json
├── tsconfig.json
├── middleware.ts                  # Protege rutas; redirige a /login si no hay cookie sas_token
├── next-env.d.ts
├── Dockerfile
├── app/
│   ├── layout.tsx                 # RootLayout + AuthProvider
│   ├── page.tsx                   # Dashboard (RequireAuth + SasDashboard)
│   ├── globals.css
│   ├── login/page.tsx             # Pantalla de login
│   ├── personas/page.tsx
│   ├── turnos/page.tsx
│   ├── asignaciones/page.tsx
│   ├── asistencias/page.tsx
│   ├── dispositivos/page.tsx
│   ├── erp/page.tsx
│   ├── logs/page.tsx
│   ├── usuarios/page.tsx
│   ├── empresas/page.tsx
│   └── api/                       # ⭐ Proxy REST → backend Flask
│       ├── _proxy.ts              # Función proxyJsonRequest
│       ├── auth/{login,register,me,...}/route.ts
│       ├── personas/{route.ts, [personaId]/route.ts, [personaId]/huella/route.ts}
│       ├── facial/{registrar,actualizar/[personaId]}/route.ts
│       ├── turnos/[turnoId]/route.ts
│       ├── asignaciones/{route.ts, [asignacionId]/route.ts}
│       ├── asistencias/{route.ts, sync/route.ts}
│       ├── dispositivos/{route.ts, [dispositivoId]/route.ts, verificar/route.ts, erp-config/route.ts}
│       ├── erp/{route.ts, [erpId]/{route.ts,test,enviar,estado}}
│       └── logs/route.ts
├── components/
│   ├── SasDashboard.tsx           # ⭐ Componente principal del panel (~2000 líneas)
│   ├── LoginForm.tsx
│   └── RequireAuth.tsx
└── lib/
    ├── api.ts                     # Cliente REST no autenticado
    ├── auth-api.ts                # Cliente REST autenticado (inyecta Bearer)
    ├── auth-context.tsx           # AuthProvider + useAuth()
    ├── auth-types.ts              # AuthUser, EmpresaVinculada
    └── types.ts                   # Persona, Turno, Asignacion, Asistencia, etc.
```

### 3.3 Patrón Proxy

El frontend **nunca** llama directamente al backend Flask. Todas las llamadas van a `/api/...` dentro del propio Next.js, que las re-envía al backend.

`Frontend/app/api/_proxy.ts`:
- Lee `FLASK_API_BASE_URL` o `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:5000`).
- Reenvía headers `Authorization` y `X-Device-MAC`.
- Devuelve JSON o texto, preservando código HTTP.
- Detección básica de bloqueo Cloudflare (status 403 con HTML) → 502 con mensaje accionable.

Cada `route.ts` es un wrapper mínimo (1-8 líneas) que llama a `proxyJsonRequest(path, init, request)`.

### 3.4 Autenticación del frontend

- `middleware.ts`: rutas no públicas (`/login`, `/api/auth` son libres) → si falta cookie `sas_token` → redirige a `/login`.
- `lib/auth-context.tsx`:
  - `AuthProvider` envuelve toda la app en `app/layout.tsx`.
  - Al montar, si hay token en `localStorage`, llama a `/api/auth/me` para obtener el usuario.
  - `useAuth()` expone `{user, loading, login, logout}`.
- `lib/auth-api.ts`:
  - `loginRequest(email, password, empresaId?)` → guarda token en `localStorage` y `document.cookie`.
  - Soporta el caso "need_empresa" (multi-empresa) devolviendo el array de empresas para que el usuario elija.

### 3.5 Dashboard principal (`SasDashboard.tsx`)

Componente monolítico controlado por estado interno `section: Section`. Las secciones disponibles son:

| Sección | Ruta | Roles |
|---|---|---|
| Dashboard | `/` | todos |
| Asistencias | `/asistencias` | todos |
| Personas | `/personas` | admin, empleador |
| Turnos | `/turnos` | admin, empleador |
| Asignaciones | `/asignaciones` | admin, empleador |
| Dispositivos | `/dispositivos` | admin, empleador |
| ERP | `/erp` | admin, empleador |
| Logs | `/logs` | admin, empleador |
| Usuarios | `/usuarios` | admin, empleador ("Mi cuenta" para trabajador) |
| Empresas | `/empresas` | solo admin |

Características clave:
- Carga lazy: cada `useEffect([section])` pide solo los datos que esa sección necesita.
- Modales para crear: persona, turno, asignación, ERP, usuario, empresa, dispositivo, contraseña.
- Toasts efímeros (3.2 s).
- Generación de PIN de enrolamiento para nuevos ESP32.
- Verificación de dispositivo por IP (`GET http://<ip>/estado` vía `/api/dispositivos/verificar`).
- Export CSV de asistencias.
- Subida de rostro vía file picker → Base64 → `POST /api/facial/registrar`.

### 3.6 Roles y UI

| Rol | Ve |
|---|---|
| **admin** | Todo, incluida gestión de empresas |
| **empleador** | Personas, turnos, asignaciones, dispositivos, ERP, logs, usuarios de su empresa |
| **trabajador** | Solo "Mi cuenta" (cambiar contraseña) + su historial de asistencia |

---

## 4. ESP32-CAM (firmware Arduino)

### 4.1 Hardware

| Componente | Rol |
|---|---|
| ESP32-CAM (AI-Thinker) | MCU + cámara OV2640 |
| Flash LED (GPIO 4) | Iluminación para captura |
| PIR (GPIO 12) | Detección de presencia (opcional) |
| **AS608 (opcional)** — UART2 (GPIO 14 RX / 15 TX) | Sensor de huella dactilar |
| LittleFS / SPIFFS | Persistencia local |

Hay **dos firmwares**:
- `esp32-cam/esp32/esp32.ino` — con sensor de huella AS608 (LittleFS).
- `esp32-cam/esp32-sin-lector/esp32-sin-lector.ino` — solo facial, sin AS608 (SPIFFS). Se usa cuando el sensor está defectuoso.

### 4.2 Conectividad

- **WiFi STA** a la red configurada (SSID/pass guardados en `/wifi.json`).
- **WiFi AP de fallback**: SSID `ESP32-ASISTENCIA`, PASS `Asistencia2026` (versión con lector) o `12345678` (sin lector), IP `192.168.4.1`. Se activa si WiFi STA falla 5 veces seguidas.
- **MQTT** vía `mqtt_client` (esp-mqtt): soporta `mqtt://`, `ws://` y `wss://` (Cloudflare). Se autoconfigura y mantiene conexión.
- **HTTP** vía `HTTPClient`: header `X-Device-MAC` en cada request.

### 4.3 Servidor web local (puerto 80, LittleFS/SPIFFS)

Sirve páginas HTML estáticas desde `/data/`:

| Página | Función |
|---|---|
| `index.html` | Menú principal (online/offline, enrolado, registro, gestión, logs, sync, WiFi) |
| `register.html` | Wizard 3 pasos: huella 1 → huella 2 → rostro |
| `gestion.html` | Crear turno, asignar turno |
| `personas.html` | Listado de personas con edición y borrado |
| `asistencias.html` | Listado de marcajes |
| `turnos.html` | Listado de turnos |
| `asignaciones.html` | Listado de asignaciones |
| `logs.html` | Logs del sistema |
| `wifi-setup.html` | Configurar SSID/pass + URL backend + broker MQTT + PIN |

Endpoints JSON/REST internos (handlers WebServer):

| Método | Ruta | Acción |
|---|---|---|
| GET | `/estado` | Estado online/enrolado/codigo_paso/rostro_ok |
| POST | `/wifi-setup` | Guardar config WiFi + backend + MQTT + PIN + reiniciar |
| POST | `/registrar?name=&rut=&email=` | Inicia registro biométrico (estado máquina: huella1→huella2→rostro) |
| POST | `/asignar-turno?persona=&turno=` | Asignar turno a persona |
| POST | `/crear-turno?nombre=&inicio=&fin=&dias=` | Crear turno |
| POST | `/marcar-asistencia` | Lee huella del AS608 y procesa marcaje (solo versión con lector) |
| POST | `/sincronizar` | Ejecuta sync manual |
| POST | `/fetch-personas` | Pull `GET /api/personas` y guarda en SPIFFS |
| POST | `/limpiar?codigo=1234` | Borrar todo el SPIFFS y huellas AS608 (solo versión con lector) |
| POST | `/set-backend?url=` | Cambiar URL del backend |
| POST | `/editar-persona?id=&name=&email=` | Editar persona local + push PATCH |
| POST | `/borrar-persona?id=` | DELETE remoto + local |
| POST | `/borrar-turno?id=` | DELETE remoto + local |
| POST | `/borrar-asignacion?persona=&turno=` | DELETE remoto + local |
| POST | `/actualizar-huella?id=&slot=` | Reasignar slot de huella (solo con lector) |
| POST | `/actualizar-rostro?id=` | Poner al sistema en modo registro facial para `id` |
| GET | `/personas.json`, `/turnos.json`, `/asignaciones.json`, `/asistencias.json` | Sirve el JSON local |
| GET | `/ultimo_registro` | Devuelve `{id, nombre, rut, imagen_url}` del último enrolamiento |
| GET | `/erp-config.json` | Config ERP descargada del backend |

### 4.4 Máquina de estados de registro biométrico

```
ESTADO_IDLE (0)
   │  (POST /registrar)
   ▼
ESTADO_ESPERANDO_HUELLA_REGISTRO (1)   ← solo versión con lector
   │  getImage() OK → image2Tz() OK → fingerSearch() falla (1ª huella)
   ▼
ESTADO_REGISTRO_SEGUNDA_HUELLA (2)
   │  2ª huella, image2Tz → createModel → storeModel(slotRegistrando)
   ▼
ESTADO_REGISTRO_FACIAL (3)
   │  llamar cámara → publicar MQTT esp32/imagen/registrar
   │  esperar respuesta en esp32/respuesta/facial
   ▼
ESTADO_IDLE (0)   ← rostroRegistroExitoso = true
```

### 4.5 Flujo de identificación (centinela automático)

```
loop cada 6 s (FACE_CHECK_INTERVAL):
  si cámara OK + online + estado IDLE:
    capturarImagenBase64() (calidad 10)
    POST /api/facial/identificar con octet-stream
    si HTTP 200 + persona_id:
      procesarAsistencia(personaId, "facial") → alterna entrada/salida
      flashExito() + LED parpadea 2x
    si HTTP 404 (rostro no reconocido): silencioso
    cooldown 8 s entre marcajes
```

Adicionalmente, si el dispositivo **no tiene internet** pero tiene personas y asignaciones en SPIFFS, procesa la asistencia **offline** y la marca como `sincronizado=false` para subirla luego en bloque.

### 4.6 Persistencia local (SPIFFS/LittleFS)

| Archivo | Contenido |
|---|---|
| `/wifi.json` | `{ssid, pass, backend, mqtt, pin}` |
| `/personas.json` | Array de personas (id, nombre, rut, email, huella_id, fecha_registro, sincronizado) |
| `/turnos.json` | Array de turnos (id, backend_id, nombre, inicio, fin, dias, sincronizado) |
| `/asignaciones.json` | Array de asignaciones |
| `/asistencias.json` | Array de marcajes con flag `sincronizado` |
| `/erp-config.json` | Configuración ERP descargada del backend |

Los IDs locales tienen el prefijo `local-` cuando aún no se sincronizaron con el backend.

### 4.7 Sincronización bidireccional

**Push (ESP32 → backend)**:
- `sincronizarAsistencias()`: POST `/api/asistencias/sync` con todos los registros `sincronizado=false`.
- `sincronizarTurnosPendientes()` y `sincronizarAsignacionesPendientes()`: empuja lo que se creó offline.

**Pull (backend → ESP32)**:
- `sincronizarPersonasDesdeBackend()`: GET `/api/personas`, sobreescribe `/personas.json`.
- `sincronizarTurnosDesdeBackend()` y `sincronizarAsignacionesDesdeBackend()`: similar.
- `sincronizarErpConfigDesdeBackend()`: GET `/api/dispositivos/erp-config`.

### 4.8 MQTT — tópicos

| Tópico | Dirección | Propósito |
|---|---|---|
| `esp32/imagen/registrar` | ESP32 → broker → backend | Enrolamiento facial (con consentimiento ya verificado en backend) |
| `esp32/respuesta/facial` | backend → broker → ESP32 | Resultado de enrolamiento (ok/error) |
| `esp32/heartbeat/<mac>` | ESP32 → broker → backend | Heartbeat cada X segundos |
| `esp32/lwt/<mac>` | broker → backend | Last Will: dispositivo desconectado |
| `esp32/asistencia/#` | ESP32 → broker | Marcajes (informativo) |
| `esp32/imagen/start` / `part` / `end` | ESP32 → broker | Protocolo de fragmentación legacy (ya no se usa, se envía un solo mensaje) |
| `esp32/imagen/eco` | backend → broker | Test bidireccional al conectar |

### 4.9 Watchdog de dispositivo

- Marca inicial: todos los dispositivos `inactivo` esperando heartbeat.
- Cada 60 s: si `tiempo_actual - ultimo_heartbeat > 90 s` para alguna MAC → marca `inactivo`.
- Si 5 reconexiones WiFi fallan → modo AP fallback.

---

## 5. Seguridad y cumplimiento (Seguridad.md)

Implementado en el backend, MQTT handler y reflejando en el flujo del ESP32.

### 5.1 Consentimiento biométrico

- Tabla `consentimientos(persona_id UNIQUE, fecha_aceptacion, version_politica, ip_dispositivo, metodo_aceptacion)`.
- **Registro desde web**: `POST /api/personas/<id>/consentimiento` (`routes/personas.py`).
- **Verificación en el backend** antes de guardar embedding:
  - `routes/facial.py:registrar_facial()` → 403 si no hay consentimiento.
  - `mqtt_handler.py:procesar_imagen_facial()` → publica error en `esp32/respuesta/facial`.
- Flujo operativo:
  1. El admin crea la persona desde el panel web.
  2. La persona (o el admin en su nombre) acepta la política → se inserta `consentimientos`.
  3. La persona va al ESP32 y se le toma la foto → backend verifica y guarda embedding.

### 5.2 Cifrado AES de embeddings

- `Backend/encryption.py` (Fernet = AES-128-CBC + HMAC-SHA256).
- Clave derivada de `BIOMETRIC_KEY` (env var) vía SHA-256 → base64.
- Aplicado en: `facial.py` (registro, actualizar, verificar, identificar) y `mqtt_handler.py` (registro).
- Retrocompatibilidad: `descifrar_embedding()` hace fallback a `json.loads` si el valor no está en formato Fernet (embeddings antiguos).
- **Sin migración retroactiva explícita**: los nuevos embeddings se cifran al guardar; los antiguos siguen funcionando hasta que se actualicen.

### 5.3 Log de acceso biométrico

- Tabla `logs_biometricos(persona_id, dispositivo_id, timestamp, tipo_operacion, resultado, ip_origen)`.
- `tipo_operacion ∈ {registro, verificacion, identificacion, eliminacion}`.
- `resultado ∈ {exito, fallo, duplicado, no_encontrado}`.
- Helper `facial.py::_log_biometrico()` se llama en cada operación (éxito/fallo).

### 5.4 Derecho al olvido

- Endpoint `DELETE /api/personas/<id>/datos-biometricos` (`routes/personas.py`).
- Acciones:
  1. Inserta registro en `eliminaciones_biometricas` con el embedding anterior, foto path y usuario solicitante.
  2. `UPDATE personas SET encoding_facial = NULL, huella_id = NULL`.
  3. Borra `static/previews/<id>.jpg`.
  4. Borra `consentimientos WHERE persona_id = ?`.
- **Las asistencias se conservan** (están disociadas del dato biométrico).

---

## 6. Orquestación (Docker Compose)

Archivo raíz: `docker-compose.yml`

| Servicio | Imagen | Puerto host | Variables | Volúmenes |
|---|---|---|---|---|
| `postgres` | `postgres:15` | 5432 | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `postgres_data:/var/lib/postgresql/data` |
| `mosquitto` | `eclipse-mosquitto:latest` | 1884 (mqtt), 9001 (ws) | – | `mosquitto_data`, `mosquitto_log`, config montado |
| `backend` | build `./Backend` | 5000 | `DATABASE_URL`, `JWT_SECRET`, `BIOMETRIC_KEY`, `MQTT_HOST`, `MQTT_PORT` | `backend_static:/app/static`, `deepface_models:/root/.deepface` |
| `frontend` | build `./Frontend` | 3000 | `FLASK_API_BASE_URL=http://backend:5000` | – |

Red bridge: `teleasist_network`.

Orden de arranque: `postgres` (healthcheck) + `mosquitto` → `backend` (depende de los dos) → `frontend` (depende del backend).

---

## 7. Flujos end-to-end clave

### 7.1 Login web
```
Browser        Next.js           Flask
  │ ─────────►  /login  (form)  │
  │                              │
  │  POST /api/auth/login        │
  │ ───────────────────────────► │  proxyJsonRequest
  │                              │  ──► POST /api/auth/login
  │                              │      bcrypt.checkpw + jwt.encode
  │  { ok, token, user }         │
  │ ◄─────────────────────────── │
  │  localStorage.sas_token=...  │
  │  document.cookie=sas_token=… │
  │  AuthProvider.setUser(user)  │
  │  redirect → / (dashboard)    │
```

### 7.2 Enrolamiento biométrico de una persona
```
1. Admin (web)    POST /api/personas       → crea persona (sin biometría)
2. Admin (web)    POST /api/personas/<id>/consentimiento
                                        → inserta en `consentimientos`
3. Trabajador     Acude al ESP32
4. ESP32          local /registrar?name=&rut=&email=
                  → estado = ESPERANDO_HUELLA_REGISTRO
5. Trabajador     Pone dedo (2 veces)   → AS608.storeModel(slot)
6. ESP32          capturarImagenBase64()
                  publish MQTT esp32/imagen/registrar
                                  {persona_id, imagen_b64}
7. Backend        mqtt_handler.procesar_imagen_facial()
                  ✓ verifica consentimiento
                  ✓ decode base64 → save static/previews/<id>.jpg
                  ✓ DeepFace.represent(Facenet, retinaface)
                  ✓ cifrar_embedding() → UPDATE personas.encoding_facial
                  ✓ INSERT logs_biometricos
                  publish esp32/respuesta/facial {status: ok, file_name}
8. ESP32          flashExito() + muestra preview
```

### 7.3 Marcaje automático (centinela)
```
loop cada 6 s:
  ESP32           identificarPorRostro()
                  → POST /api/facial/identificar (octet-stream)
  Backend         descifrar_embedding(para cada persona) → comparación
                  → best match
                  si distancia < 10:
                     INSERT logs_biometricos (exito)
                     return { persona_id }
                  si no:
                     INSERT logs_biometricos (fallo)
                     return 404
  ESP32           procesarAsistencia(persona_id, "facial")
                  → alterna entrada/salida
                  → POST /api/asistencias
  Backend         INSERT asistencias
                  → threading.Thread(erp_push_async(...))
  ERP webhook     POST con payload transformado por field_map
```

### 7.4 Sincronización bidireccional
```
ESP32 (boot/loop)              Backend
  GET /api/personas  ────────►   SELECT personas WHERE empresa_id
  ◄────── personas.json ──────  serializa a JSON
  save /personas.json
  ...
  POST /api/asistencias/sync ──► bulk insert con dedupe 60s
  ◄────── {ok, insertados, errores} ──
  marca como sincronizado=true
```

---

## 8. Configuración de variables de entorno

`Backend/.env` (real, en producción Neon):
```
DATABASE_URL=postgresql://…neon.tech/neondb?sslmode=require&channel_binding=require
JWT_SECRET=…
BIOMETRIC_KEY=…
MQTT_HOST=mosquitto
MQTT_PORT=1883
```

`.env.example` (plantilla):
```
POSTGRES_USER=sas
POSTGRES_PASSWORD=sas123
POSTGRES_DB=sas_db
DATABASE_URL=postgresql://sas:sas123@postgres:5432/sas_db
JWT_SECRET=cambia-esta-clave-en-produccion
BIOMETRIC_KEY=cambia-esta-clave-biometrica-en-produccion
MQTT_HOST=mosquitto
MQTT_PORT=1883
FLASK_API_BASE_URL=http://backend:5000
```

`Frontend` (env):
- `FLASK_API_BASE_URL` — usado por el contenedor del frontend para apuntar al backend.
- `NEXT_PUBLIC_DEVICE_BASE_URL` — opcional, base para abrir el panel del ESP32 desde el dashboard.

ESP32 (config local en `/wifi.json`):
- `ssid`, `pass`, `backend` (URL Flask), `mqtt` (URL broker, soporta `ws://`, `wss://`, `mqtt://`), `pin` (PIN de enrolamiento).

---

## 9. Estado del proyecto y pendientes

### Implementado
- Backend Flask con biometría, JWT, multi-empresa, roles, ERP.
- Frontend Next.js con dashboard, formularios, proxy REST.
- ESP32-CAM con cámara, huella (opcional), WiFi STA+AP, MQTT, servidor web local, sync bidireccional.
- Docker Compose para los 4 servicios.
- **Cifrado AES de embeddings, consentimiento biométrico, logs de auditoría, derecho al olvido** (Seguridad.md aplicado en backend + MQTT handler).

### Áreas pendientes / mejoras sugeridas
- Cifrado AES de los **datos locales en SPIFFS/LittleFS** del ESP32 (huella AS608 y embeddings cacheados).
- HTTPS obligatorio para producción (Cloudflare tunnel en pruebas).
- Cifrado de las **huellas en la BD** (campo `huella_id` actualmente solo guarda el slot 1-127, no el template).
- Política de retención y borrado periódico de `static/previews/`.
- Rate-limiting en endpoints sensibles.
- Tests automatizados (no hay suite formal, solo `tests/mqtt.py` y `tests/test.py` sueltos).
- Migrations versionadas (actualmente esquema evoluciona con `ALTER TABLE IF NOT EXISTS`).
- `static/previews/` montado como volumen `backend_static` en Docker — bien para persistencia, mal para backups cifrados.

---

## 10. Referencias rápidas de archivos clave

| Tema | Archivo |
|---|---|
| Entry point backend | `Backend/app.py` |
| Esquema BD | `Backend/database.py`, `Backend/DB/schema.sql` |
| Cifrado biométrico | `Backend/encryption.py` |
| Reconocimiento facial | `Backend/routes/facial.py` |
| Cons. MQTT | `Backend/mqtt_handler.py` |
| Auth/JWT | `Backend/routes/auth.py` |
| Proxy REST | `Frontend/app/api/_proxy.ts` |
| Dashboard | `Frontend/components/SasDashboard.tsx` |
| Auth frontend | `Frontend/lib/auth-context.tsx`, `Frontend/lib/auth-api.ts` |
| Firmware ESP32 | `esp32-cam/esp32/esp32.ino` |
| Firmware ESP32 sin lector | `esp32-cam/esp32-sin-lector/esp32-sin-lector.ino` |
| UI local ESP32 | `esp32-cam/esp32/data/*.html` |
| Docker | `docker-compose.yml` (raíz) |
