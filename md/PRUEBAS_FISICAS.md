# Pruebas del Prototipo — Automaticas vs Fisicas

> **Actualizado**: 2026-06-16 — Suite de tests pytest (243 tests) + contraseñas dispositivos + Vitest (32 tests) + Playwright (9 tests).

Corresponden a las pruebas descritas en `Informe/cap4_iteraciones.tex`. Las pruebas se dividen en tres categorias:

- **A** Automatizada (pytest/Vitest/Playwright) — cubierta por la suite en `Backend/tests/` y `Frontend/__tests__/`
- **E** Emulada — cubierta por `Backend/tests/esp32_emulator/`
- **H** Hardware — requiere ESP32-CAM fisico (camara OV2640, lector AS608, sensor PIR, GPIOs)

---

## Iteracion 1: Integracion de hardware y servidor embebido

| # | Prueba | Tipo | Procedimiento | Resultado esperado |
|---|---|---|---|---|
| 1.1 | Captura de imagenes | **H** | Encender ESP32-CAM, verificar `esp_camera_fb_get()` retorne buffers JPEG sin corrupcion | Buffer consistente, sin frames negros |
| 1.2 | Comunicacion UART AS608 | **H** | Verificar `finger.verifyPassword()` retorne `FINGERPRINT_OK` en <1s | Conexion a 57600 baud sin perdida de paquetes |
| 1.3 | Lectura biometrica | **H** | Capturar huella: `getImage()` → `image2Tz()` → `storeModel()` | Proceso <2s, slot almacenado 1-127 |
| 1.4 | Acceso via AP | **H** | Sin WiFi, conectar a `ESP32-ASISTENCIA` / `Asistencia2026`, abrir `192.168.4.1` | Todas las rutas HTML responden HTTP 200 |
| 1.5 | Carga de vistas via WiFi | **H** | Conectar ESP32 a red externa, acceder a IP asignada por router | Vistas cargan con CSS/JS intactos |

---

## Iteracion 2: Almacenamiento local y modo offline

| # | Prueba | Tipo | Procedimiento | Resultado esperado |
|---|---|---|---|---|
| 2.1 | Persistencia tras reinicio | **H** | Registrar datos → cortar energia → reiniciar | JSON conservan contenido integro |
| 2.2 | Lectura y deserializacion | **H** | Abrir cada `.json` via endpoint desde web embebida | `ArduinoJson` deserializa sin errores |
| 2.3 | Escritura concurrente | **H** | Registrar persona + turno + asistencia en rapida sucesion | Sin corrupcion ni perdida de datos |
| 2.4 | Marcacion offline por huella | **H** | Desconectar WiFi, registrar con huella, marcar asistencia | `sincronizado=false` en `asistencias.json` |
| 2.5 | Alternancia entrada/salida | **A** | Marcar 2 veces mismo usuario via API | Test: `test_emulador_marcaje_asistencia.py` |
| 2.6 | Validacion de turno offline | **H** | Marcar usuario sin turno asignado | Rechazo "Sin turno asignado" |
| 2.7 | Funcionamiento AP | **H** | Desconectar toda red, verificar AP activo | Operaciones desde `192.168.4.1` |

---

## Iteracion 3: Comunicacion WiFi, MQTT y HTTP

| # | Prueba | Tipo | Procedimiento | Resultado esperado |
|---|---|---|---|---|
| 3.1 | Conexion y reconexion WiFi | **H** | Configurar credenciales → apagar/encender router | Reconexion <30s tras recuperar senal |
| 3.2 | Envio MQTT (registro facial) | **A** | Capturar imagen → publicar `esp32/imagen/registrar` | Test: `test_routes_facial.py` + `test_registro_facial_mqtt.py` |
| 3.3 | Heartbeat y LWT | **A/E** | Heartbeat via MQTT mock + LWT | Test: `test_heartbeat_watchdog.py` + `test_mqtt_handler.py`. LWT real requiere broker fisico |
| 3.4 | Sincronizacion por lotes | **E** | Simular 5 marcaciones offline → POST `/api/asistencias/sync` que  | Test: `test_sync_offline.py` |
| 3.5 | Latencia MQTT | **H** | Medir publish→respuesta en `esp32/respuesta/facial` | <5s en red local. Cronometro manual |

---

## Iteracion 4: Reconocimiento facial, anti-spoofing, cifrado

| # | Prueba | Tipo | Procedimiento | Resultado esperado |
|---|---|---|---|---|
| 4.1 | Registro facial exitoso | **A** | `POST /api/facial/registrar` con consentimiento | Test: `test_routes_facial.py::test_registrar_con_consentimiento_exitoso` |
| 4.2 | Deteccion de duplicados | **A** | Registrar 2da foto del mismo rostro con otro `persona_id` | Test: `test_routes_facial.py::test_registrar_duplicado_rechazado` (HTTP 409) |
| 4.3 | Rechazo sin consentimiento | **A** | Registrar rostro sin consentimiento | Test: `test_routes_facial.py::test_registrar_sin_consentimiento_falla` (HTTP 403) |
| 4.4 | Identificacion 1:N | **E** | Registrar 3 personas → identificar una | Test: `test_identificacion_facial.py` |
| 4.5 | Rostro desconocido | **E** | Enviar foto de persona NO registrada | Test: `test_identificacion_facial.py` (HTTP 404) |
| 4.6 | Anti-spoofing (foto impresa) | **H** | Foto impresa frente a camara | DeepFace lanza `ValueError("Spoof detected")` |
| 4.7 | Iluminacion variable | **H** | Capturar con luz natural / tenue / contraluz | 3 embeddings con distancia <10.0 entre si |
| 4.8 | Cifrado de embeddings | **A** | Almacenar y recuperar embedding | Test: `test_encryption.py` (round-trip, IV, tampering) |
| 4.9 | Eliminacion biometrica | **A** | `DELETE /api/personas/<id>/datos-biometricos` | Test: `test_routes_personas.py::test_eliminar_datos_biometricos` |

---

## Iteracion 5: Autenticacion, multi-tenant, enrolamiento

| # | Prueba | Tipo | Procedimiento | Resultado esperado |
|---|---|---|---|---|
| 5.1 | Login exitoso | **A** | `POST /api/auth/login` admin@empresa.cl / admin123 | Test: `test_routes_auth.py::test_login_exitoso_admin` |
| 5.2 | Multiples empresas | **A** | Usuario con 2+ empresas, login sin `empresa_id` | Test: `test_routes_auth.py` (login flow con need_empresa) |
| 5.3 | Credenciales invalidas | **A** | Login con password incorrecta | Test: `test_routes_auth.py::test_login_password_incorrecta` (HTTP 401) |
| 5.4 | Acceso sin token | **A** | Endpoint protegido sin Authorization | Test: `test_routes_auth.py::test_me_sin_token` (HTTP 401) |
| 5.5 | Rol insuficiente | **A** | Trabajador intenta crear usuario | Test: `test_routes_auth.py::test_trabajador_no_puede_crear_usuarios` (HTTP 403) |
| 5.6 | Aislamiento multi-tenant | **A** | Empleador A consulta `GET /api/personas` | Test: `test_routes_personas.py::test_aislamiento_multi_tenant_empleador` |
| 5.7 | Generacion de PIN | **A** | `POST /api/dispositivos/generar-pin` | Test: `test_routes_auth.py::test_generar_pin_dispositivo` |
| 5.8 | Enrolamiento exitoso | **E** | `POST /api/dispositivos/enrolar` con PIN+MAC+IP | Test: `test_enrolamiento.py` (PIN consumido, no reutilizable) |
| 5.9 | Heartbeat y estado | **A** | Dispositivo enrolado envia heartbeat → detener >90s | Test: `test_mqtt_handler.py::test_device_watchdog_sweep_inicial` |
| 5.10 | LWT | **H** | Conectar ESP32 → cortar energia abruptamente | Broker publica LWT real, backend marca `inactivo` |
| 5.11 | Generacion de contraseña desde backend | **A** | `POST /api/dispositivos/<id>/generar-password` | Test: `test_generar_password_exito` (HTTP 200, password 12 chars) |
| 5.12 | Sincronizacion de contraseña al ESP32 | **E** | ESP32 consulta `GET /api/dispositivos/check-password` c/60s | Test: `test_check_password_pendiente_true` + `test_confirmar_password_exito` |
| 5.13 | Confirmacion de contraseña aplicada | **A** | `POST /api/dispositivos/confirmar-password` limpia flag pendiente | Test: `test_confirmar_password_exito` verifica `pendiente: False` |
| 5.14 | Eliminacion de contraseña | **A** | `DELETE /api/dispositivos/<id>/password` libera dispositivo | Test: `test_eliminar_password_exito` |
| 5.15 | Contraseña pendiente offline | **H** | Generar contraseña con ESP32 desconectado → reconectar | ESP32 aplica contraseña al conectar. Test manual con hardware |

---

## Iteracion 6: Modulo antifraude (PIR, flash, cooldown)

**TODAS requieren hardware fisico.** Ninguna es automatizable sin la placa ESP32-CAM.

| # | Prueba | Tipo | Procedimiento | Resultado esperado |
|---|---|---|---|---|
| 6.1 | Deteccion PIR | **H** | Persona a 50 cm del dispositivo | PIR detecta en <1s. Sin persona >15s → reposo |
| 6.2 | Falsos positivos PIR | **H** | Dispositivo 10 min en habitacion vacia | Max 1 falso positivo por hora |
| 6.3 | Cooldown entre marcaciones | **H** | Marcar por huella → intentar inmediatamente otra | Rechazo durante 8s (`COOLDOWN_TIEMPO = 8000 ms`) |
| 6.4 | Debounce de huella | **H** | Mantener dedo presionado 5s sobre AS608 | Solo 1 marcacion, no multiples |
| 6.5 | Bloqueo por menu | **H** | Abrir `/register` → intentar marcacion con huella | Bloqueado 30s (`BLOQUEO_MENU_MS = 30000 ms`) |
| 6.6 | Anti-spoofing (foto) | **H** | Foto impresa del rostro frente al PIR | DeepFace rechaza, HTTP 400 |
| 6.7 | Anti-spoofing (pantalla) | **H** | Video del rostro en telefono frente al ESP32 | Sistema rechaza identificacion |
| 6.8 | Flash PWM | **H** | Medir con osciloscopio durante captura | Flash al 50% duty, <200ms |
| 6.9 | Senalizacion flash | **H** | Marcacion exitosa: 2 destellos. Error: 1 largo | `flashExito()` y `flashError()` visibles |

---

## Iteracion 7: Panel web e integracion ERP

| # | Prueba | Tipo | Procedimiento | Resultado esperado |
|---|---|---|---|---|
| 7.1 | Navegacion panel web | **A** | Login → dashboard | Test Playwright: `dashboard.spec.ts` |
| 7.2 | Creacion integracion ERP | **A** | `POST /api/erp` | Test: `test_routes_sync_erp.py::TestRoutesErp::test_crear_erp_generic` |
| 7.3 | Test de webhook | **A** | `POST /api/erp/<id>/test` | Test: `test_routes_sync_erp.py::TestRoutesErp::test_test_webhook_exitoso` |
| 7.4 | Envio automatico | **A** | Asistencia → webhook destino | Test: `test_erp_push.py` + `mock_requests_post` |
| 7.5 | Field mapping | **A** | ERP con `{"persona_id":"employee_id"}` | Test: `test_routes_sync_erp.py::TestRoutesErp::test_transformar_datos_static` |
| 7.6 | Envio asincrono | **A** | Webhook lento (5s) → respuesta al cliente <200ms | Test: `test_routes_sync_erp.py` (mock_thread verifica thread lanzado) |
| 7.7 | Tolerancia a fallos ERP | **A** | Webhook retorna HTTP 500 | Test: `test_routes_sync_erp.py::TestRoutesErp::test_enviar_a_webhook_failure` |
| 7.8 | ERP config sync a ESP32 | **A/E** | `GET /api/dispositivos/erp-config` | Test: `test_routes_sync_erp.py::TestRoutesDispositivos::test_erp_config_dispositivo` + `test_erp_push.py` |
| 7.9 | Envio manual por lote | **A** | `POST /api/erp/<id>/enviar` | Test: `test_routes_sync_erp.py::TestRoutesErp::test_erp_enviar_manual` |

---

## Iteracion 8: Sincronizacion diferida, logs y flujo completo

| # | Prueba | Tipo | Procedimiento | Resultado esperado |
|---|---|---|---|---|
| 8.1 | Sincronizacion asistencias offline | **E** | 5 marcaciones → reconectar → sincronizar | Test: `test_sync_offline.py` (5 registros en BD) |
| 8.2 | Idempotencia de sincronizacion | **A** | Sincronizar → volver a sincronizar sin nuevos registros | Test: `test_routes_sync_erp.py` (dedup 60s ventana) |
| 8.3 | Sincronizacion personas offline | **H** | Crear persona con huella offline → reconectar | Persona con ID definitivo del backend |
| 8.4 | Sincronizacion turnos offline | **E** | Crear turno y asignacion offline → sincronizar | Test: `test_sync_offline.py::test_sync_crea_turno_y_asignacion` |
| 8.5 | Persistencia tras corte energia | **H** | Cortar alimentacion DURANTE sincronizacion | JSON no corruptos, `sincronizado=false` conservados |
| 8.6 | Logs de sincronizacion | **A** | 3 sincronizaciones con cantidades distintas | Test: `test_routes_general.py::TestRoutesLogs` |
| 8.7 | Logs biometricos | **A** | Registro + identificacion exitosa + fallida + verificacion | Test: `test_routes_facial.py` (logs_biometricos poblada via _log_biometrico) |
| 8.8 | Watchdog | **A** | Iniciar backend → conectar ESP32 → desconectar ESP32 | Test: `test_mqtt_handler.py::test_device_watchdog_sweep_inicial` |
| 8.9 | Simulacion facial | **A** | Ejecutar tests faciales con imagenes sinteticas | Test: `test_routes_facial.py` (no requiere hardware) |
| 8.10 | Flujo punta a punta | **H** | Registro completo: persona + huella + rostro → sync → ERP | Requiere todos los componentes integrados |

---

## Resumen: cobertura de pruebas

| Iteracion | Total | Automatizadas (A) | Emuladas (E) | Hardware (H) |
|---|---|---|---|---|
| 1 | 5 | 0 | 0 | 5 |
| 2 | 7 | 1 | 0 | 6 |
| 3 | 5 | 2 | 2 | 1 |
| 4 | 9 | 6 | 1 | 2 |
| 5 | 15 | 13 | 1 | 1 |
| 6 | 9 | 0 | 0 | 9 |
| 7 | 9 | 9 | 0 | 0 |
| 8 | 10 | 4 | 3 | 3 |
| **Total** | **69** | **35** | **7** | **27** |

### Suite automatizada

| Suite | Ubicacion | Comando |
|---|---|---|
| Backend (pytest) | `Backend/tests/` | `pytest Backend/tests -v` |
| Emulador ESP32 | `Backend/tests/esp32_emulator/` | `pytest Backend/tests/esp32_emulator/ -v` |
| Frontend unit (Vitest) | `Frontend/__tests__/` | `cd Frontend && npx vitest run` |
| Frontend E2E (Playwright) | `Frontend/e2e/` | `cd Frontend && npx playwright test` |

### Pruebas que requieren hardware (27)

Documentadas arriba en iteraciones 1, 2, 6 y parcialmente en 3, 4, 5, 8. Estas pruebas se ejecutan manualmente con el dispositivo ESP32-CAM fisico siguiendo los procedimientos descritos en cada tabla.

> **Nota**: Las pruebas de hardware son complementarias a la suite automatizada. La combinacion de ambas garantiza cobertura completa del sistema (backend + frontend + firmware).
