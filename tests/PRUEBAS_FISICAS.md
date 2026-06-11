# Pruebas Fisicas del Prototipo

Corresponden a las pruebas descritas en `Informe/cap4_iteraciones.tex` que **requieren el hardware ESP32-CAM** (camara OV2640, lector AS608, sensor PIR, GPIOs). No son automatizables en Python y deben ejecutarse manualmente sobre el dispositivo fisico.

---

## Iteracion 1: Integracion de hardware y servidor embebido

| # | Prueba | Procedimiento | Resultado esperado | Script/Archivo |
|---|---|---|---|---|
| 1.1 | Captura de imagenes | Encender ESP32-CAM, verificar que `esp_camera_fb_get()` retorne buffers JPEG sin corrupcion | Buffer consistente tras cada captura, sin frames negros | Firmware `esp32.ino` |
| 1.2 | Comunicacion UART AS608 | Al iniciar, verificar que `finger.verifyPassword()` retorne `FINGERPRINT_OK` en <1s | Confirmacion de conexion a 57600 baud sin perdida de paquetes | `esp32.ino:1857-1858` |
| 1.3 | Lectura biometrica | Capturar huella con `finger.getImage()` -> `image2Tz()` -> `storeModel()` | Proceso completo <2s, slot almacenado 1-127 | `esp32.ino` (flujo de enrolamiento) |
| 1.4 | Acceso via AP | Iniciar sin WiFi configurada, conectar notebook a `ESP32-ASISTENCIA` / `Asistencia2026`, abrir `192.168.4.1` | Todas las rutas (/, /register, /gestion, /personas, /asistencias, /turnos, /asignaciones, /wifi-setup, /logs) responden HTTP 200 | `esp32.ino:39-40` |
| 1.5 | Carga de vistas via WiFi | Conectar ESP32 a red externa, acceder a IP asignada por router | Vistas cargan con CSS/JS intactos, sin dependencias CDN rotas | `esp32.ino` (rutas `servirArchivo()`) |

---

## Iteracion 2: Almacenamiento local y modo offline

| # | Prueba | Procedimiento | Resultado esperado | Script/Archivo |
|---|---|---|---|---|
| 2.1 | Persistencia tras reinicio | Registrar usuarios, turnos, asignaciones, asistencias -> cortar energia -> reiniciar | Todos los archivos JSON conservan contenido integro | `data/*.json` en LittleFS |
| 2.2 | Lectura y deserializacion | Abrir cada `.json` via endpoint `/api/...` desde web embebida | `ArduinoJson` deserializa sin errores, campos completos | `esp32.ino:loadArray()` |
| 2.3 | Escritura concurrente | Registrar persona + asignar turno + marcar asistencia en rapida sucesion | Sin corrupcion ni perdida de datos | `esp32.ino:saveArray()` |
| 2.4 | Marcacion offline por huella | Desconectar WiFi, registrar usuario con huella, marcar asistencia | Registro en `asistencias.json` con `sincronizado=false` | `esp32.ino:handleMarcarAsistencia()` |
| 2.5 | Alternancia entrada/salida | Marcar 2 veces consecutivas mismo usuario | 1er registro: `"tipo":"entrada"`, 2do: `"tipo":"salida"` | `esp32.ino` (logica de alternancia) |
| 2.6 | Validacion de turno offline | Marcar usuario sin turno asignado | Rechazo con mensaje "Sin turno asignado" | `esp32.ino:turnoActivo()` |
| 2.7 | Funcionamiento AP | Desconectar toda red, verificar AP `ESP32-ASISTENCIA` activo | Todas las operaciones funcionan desde `192.168.4.1` | `esp32.ino` (modo AP fallback) |

---

## Iteracion 3: Comunicacion WiFi, MQTT y HTTP

| # | Prueba | Procedimiento | Resultado esperado | Script/Archivo |
|---|---|---|---|---|
| 3.1 | Conexion y reconexion WiFi | Configurar credenciales -> conectar -> apagar router -> encender router | Desconexion detectada via `ARDUINO_EVENT_WIFI_STA_DISCONNECTED`, reconexion <30s tras recuperar senal | `esp32.ino:verificarConexionWiFi()` |
| 3.2 | Envio MQTT (registro facial) | Capturar imagen -> publicar en `esp32/imagen/registrar` | Backend recibe, decodifica, guarda en `static/previews/`, responde por `esp32/respuesta/facial` | `esp32.ino:registrarRostroEnBackend()` + `mqtt_handler.py` |
| 3.3 | Heartbeat y LWT | Conectar ESP32 -> verificar heartbeat cada 30s en `esp32/heartbeat/<MAC>` -> cortar energia | Backend actualiza `ultimo_heartbeat`, tras corte LWT marca `inactivo` en <10s | `esp32.ino` (loop MQTT) + `mqtt_handler.py:85-126` |
| 3.4 | Sincronizacion por lotes | Generar 5 marcaciones offline -> conectar WiFi -> ejecutar sincronizacion | 5 registros llegan via `POST /api/asistencias/sync`, se marcan `sincronizado=true` | `esp32.ino:sincronizarAsistencias()` |
| 3.5 | Latencia MQTT | Medir tiempo desde `publish` en ESP32 hasta recepcion de respuesta en `esp32/respuesta/facial` | <5 segundos en red local | Cronometro manual |

---

## Iteracion 4: Reconocimiento facial, anti-spoofing, cifrado

| # | Prueba | Procedimiento | Resultado esperado | Script |
|---|---|---|---|---|
| 4.1 | Registro facial exitoso | Enviar foto + `persona_id` con consentimiento a `POST /api/facial/registrar` | HTTP 200, embedding cifrado en BD, preview en `static/previews/` | `test_facial_identificar.py` (parcial) |
| 4.2 | Deteccion de duplicados | Registrar 2da foto del mismo rostro con otro `persona_id` | HTTP 409, mensaje con nombre de la persona duplicada | Requiere backend corriendo |
| 4.3 | Rechazo sin consentimiento | Registrar rostro sin consentimiento en tabla `consentimientos` | HTTP 403 | Requiere backend corriendo |
| 4.4 | Identificacion 1:N | Registrar 3 personas con foto -> enviar foto de una de ellas | Retorna `persona_id` correcto, copia en `capturas_prueba/` | `test_facial_identificar.py` |
| 4.5 | Rostro desconocido | Enviar foto de persona NO registrada | HTTP 404, entrada en `logs_biometricos` con `resultado=no_encontrado` | `test_facial_identificar.py` |
| 4.6 | Anti-spoofing (foto impresa) | Imprimir foto de rostro registrado -> presentar frente a camara | DeepFace lanza `ValueError("Spoof detected")`, HTTP 400 | Requiere hardware |
| 4.7 | Iluminacion variable | Capturar mismo rostro con: luz natural / luz tenue / contraluz | 3 embeddings con distancia <10.0 entre si, identificacion correcta | Requiere hardware |
| 4.8 | Cifrado de embeddings | Almacenar y recuperar embedding de BD | Valor en columna `encoding_facial` ilegible, round-trip exacto | `test_cifrado_embeddings.py` (standalone) |
| 4.9 | Eliminacion biometrica | `DELETE /api/personas/<id>/datos-biometricos` | Embedding, foto y consentimiento eliminados; asistencias conservadas; entrada en `eliminaciones_biometricas` | Requiere backend corriendo |

---

## Iteracion 5: Autenticacion, multi-tenant, enrolamiento

| # | Prueba | Procedimiento | Resultado esperado | Script |
|---|---|---|---|---|
| 5.1 | Login exitoso | `POST /api/auth/login` con `admin@empresa.cl` / `admin123` | Token JWT con `user_id`, `empresa_id`, `rol=admin`, `exp=24h` | `test_auth_jwt.py` |
| 5.2 | Multiples empresas | Usuario con 2+ empresas, login sin `empresa_id` | `need_empresa=true`, lista de empresas | `test_auth_jwt.py` (parcial) |
| 5.3 | Credenciales invalidas | Login con password incorrecta | HTTP 401 | `test_auth_jwt.py` |
| 5.4 | Acceso sin token | `POST /api/auth/register` sin header Authorization | HTTP 401 | `test_auth_jwt.py` |
| 5.5 | Rol insuficiente | Trabajador intenta `POST /api/auth/register` (crear usuario) | HTTP 403 "Permisos insuficientes" | `test_auth_jwt.py` |
| 5.6 | Aislamiento multi-tenant | Empleador empresa A consulta `GET /api/personas` | Solo personas de empresa A | `test_auth_jwt.py` (parcial) |
| 5.7 | Generacion de PIN | `POST /api/dispositivos/generar-pin` como empleador | PIN 8 chars alfanumerico, `enrolado=false` en BD | Requiere backend corriendo |
| 5.8 | Enrolamiento exitoso | `POST /api/dispositivos/enrolar` con PIN+MAC+IP | `enrolado=true`, PIN consumido (no reutilizable) | Requiere backend corriendo |
| 5.9 | Heartbeat y estado | Dispositivo enrolado envia heartbeat -> detener >90s | Estado cambia `activo` -> `inactivo` via watchdog | Requiere hardware |
| 5.10 | LWT | Conectar ESP32 -> cortar energia abruptamente | Broker publica LWT, backend marca `inactivo` en <10s | Requiere hardware |

---

## Iteracion 6: Modulo antifraude (PIR, flash, cooldown)

**TODAS estas pruebas requieren hardware fisico. No automatizables.**

| # | Prueba | Procedimiento | Resultado esperado |
|---|---|---|---|
| 6.1 | Deteccion PIR | Persona a 50 cm del dispositivo | PIR detecta en <1s, sistema transiciona a modo activo. Sin persona >15s -> retorna a reposo |
| 6.2 | Falsos positivos PIR | Dispositivo 10 min en habitacion vacia | Max 1 falso positivo por hora. Logs monitorizables via `/api/logs` |
| 6.3 | Cooldown entre marcaciones | Marcar por huella -> intentar inmediatamente otra marcacion | Rechazo durante 8s (`COOLDOWN_TIEMPO = 8000 ms`) |
| 6.4 | Debounce de huella | Mantener dedo presionado 5s sobre AS608 | Solo 1 marcacion, no multiples |
| 6.5 | Bloqueo por menu | Abrir `/register` en navegador -> intentar marcacion con huella | Sistema bloqueado 30s (`BLOQUEO_MENU_MS = 30000 ms`) |
| 6.6 | Anti-spoofing (foto) | Imprimir foto rostro registrado, moverla frente al PIR | DeepFace rechaza, HTTP 400 "Spoof detected" |
| 6.7 | Anti-spoofing (pantalla) | Reproducir video del rostro en telefono frente al ESP32 | Sistema rechaza identificacion |
| 6.8 | Flash PWM | Medir con osciloscopio durante captura | Flash al 50% duty cycle, <200ms, suficiente para imagen nitida |
| 6.9 | Senalizacion flash | Marcacion exitosa: 2 destellos breves. Error: 1 destello largo | `flashExito()` y `flashError()` visibles |

---

## Iteracion 7: Panel web e integracion ERP

| # | Prueba | Procedimiento | Resultado esperado | Script |
|---|---|---|---|---|
| 7.1 | Navegacion panel web | Acceder a `/health`, `/api/personas`, `/api/asistencias` sin autenticacion | Respuesta adecuada (HTTP 200 o 401 segun endpoint) | `test_integracion_backend.py` |
| 7.2 | Creacion integracion ERP | `POST /api/erp` con nombre, tipo, webhook URL, field mapping | HTTP 200, `activo=true`, `envio_auto=true` | `test_erp_integracion.py` |
| 7.3 | Test de webhook | `POST /api/erp/<id>/test` | Webhook recibe payload con datos ficticios | `test_erp_integracion.py` |
| 7.4 | Envio automatico | Registrar asistencia -> verificar webhook destino | Datos llegan automaticamente al ERP configurado | `test_erp_integracion.py` (parcial) |
| 7.5 | Field mapping | ERP con `{"persona_id":"employee_id","tipo":"event"}` | Webhook recibe campos renombrados (`employee_id`, `event`) | `test_erp_integracion.py` (static) |
| 7.6 | Envio asincrono | ERP con webhook lento (5s) -> medir respuesta de `POST /api/asistencias` | Respuesta al cliente <200ms, envio ERP en segundo plano | Requiere mock de webhook lento |
| 7.7 | Tolerancia a fallos ERP | Webhook retorna HTTP 500 | Asistencia persiste en BD, error en `ultimo_estado` | `test_erp_integracion.py` (parcial) |
| 7.8 | ERP config sync a ESP32 | `GET /api/dispositivos/erp-config` con header X-Device-MAC | Solo integraciones activas con `envio_auto=true` de la empresa | Requiere hardware |
| 7.9 | Envio manual por lote | `POST /api/erp/<id>/enviar` | Ultimas 200 asistencias enviadas al webhook | Requiere backend corriendo |

---

## Iteracion 8: Sincronizacion diferida, logs y flujo completo

| # | Prueba | Procedimiento | Resultado esperado | Hardware |
|---|---|---|---|---|
| 8.1 | Sincronizacion asistencias offline | Desconectar -> 5 marcaciones para 2 personas -> reconectar -> sincronizar | 5 registros en BD, `sincronizado=true` en `asistencias.json` | Requiere |
| 8.2 | Idempotencia de sincronizacion | Sincronizar -> volver a sincronizar sin nuevos registros | 0 inserciones duplicadas en BD | Requiere |
| 8.3 | Sincronizacion personas offline | Crear persona con huella offline -> reconectar -> sincronizar | Persona con ID definitivo del backend (no `local-`) | Requiere |
| 8.4 | Sincronizacion turnos offline | Crear turno y asignacion offline -> reconectar -> sincronizar | Turno y asignacion en BD, `backend_id` actualizados | Requiere |
| 8.5 | Persistencia tras corte energia | Cortar alimentacion DURANTE sincronizacion | JSON no corruptos, registros `sincronizado=false` conservados | Requiere |
| 8.6 | Logs de sincronizacion | 3 sincronizaciones con cantidades distintas | 3 entradas en `sincronizacion_log` con conteos correctos | Hardware + DB |
| 8.7 | Logs biometricos | Registro facial + identificacion exitosa + identificacion fallida + verificacion | 4 entradas en `logs_biometricos` con tipo/resultado | Hardware + DB |
| 8.8 | Watchdog | Iniciar backend -> conectar ESP32 -> desconectar ESP32 | Inicio: todos inactivos. Conexion: activo. >90s sin heartbeat: inactivo | Requiere |
| 8.9 | Simulacion facial | Ejecutar `deteccion.py`, seleccionar foto de persona registrada | Coincidencia encontrada, asistencia registrada en BD | No requiere |
| 8.10 | Flujo punta a punta | Registro completo: persona + huella + rostro -> sincronizar -> marcar offline -> reconectar -> sincronizar -> verificar panel web + ERP | Datos consistentes en ESP32, backend, panel web y webhook ERP | Requiere |

---

## Resumen: cobertura de pruebas

| Iteracion | Total pruebas | Automatizadas (Python) | Requieren hardware |
|---|---|---|---|
| 1 | 5 | 0 | 5 |
| 2 | 7 | 0 | 7 |
| 3 | 5 | 1 (`test_integracion_backend.py`) | 4 |
| 4 | 9 | 2 (`test_facial_identificar.py`, `test_cifrado_embeddings.py`) | 7 |
| 5 | 10 | 1 (`test_auth_jwt.py`) | 9 |
| 6 | 9 | 0 | 9 |
| 7 | 9 | 1 (`test_erp_integracion.py`) | 8 |
| 8 | 10 | 0 | 10 |
| **Total** | **64** | **5** | **59** |

### Scripts automatizados

| Script | Ejecucion | Requisito |
|---|---|---|
| `tests/test_cifrado_embeddings.py` | `py tests/test_cifrado_embeddings.py` | Solo `cryptography` + `Backend/encryption.py` |
| `tests/test_integracion_backend.py` | `py tests/test_integracion_backend.py` | Backend corriendo + DB accesible |
| `tests/test_facial_identificar.py` | `py tests/test_facial_identificar.py` | Backend corriendo + DeepFace |
| `tests/test_auth_jwt.py` | `py tests/test_auth_jwt.py` | Backend corriendo |
| `tests/test_erp_integracion.py` | `py tests/test_erp_integracion.py [WEBHOOK_URL]` | Backend corriendo |
