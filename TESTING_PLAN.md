# Plan de Testing — Sistema de Asistencia SAS

Plan integral de pruebas para alcanzar ≥90% de cobertura sobre el backend Python (Flask), frontend TypeScript (Next.js), y emulación de ESP32-CAM.

## Estrategia

| Componente | Herramienta | Tipo |
|---|---|---|
| Backend Python | pytest + pytest-cov + pytest-flask + pytest-mock | Unitarios + Integración E2E |
| Frontend TS/TSX | Vitest + @testing-library/react + MSW | Unitarios + Componentes |
| Frontend E2E | Playwright (chromium) | E2E |
| ESP32 firmware | Emulación en Python (HTTP + MQTT mock) + PRUEBAS_FISICAS.md | Hardware manual |
| CI/CD | GitHub Actions | Automático por push/PR |

## Decisiones

- **DB**: PostgreSQL real en Docker (auto-manejado por `conftest.py`). Sin mock de psycopg2.
- **MQTT**: Mock a nivel de `paho.mqtt.client.Client` (sin broker real).
- **DeepFace**: Mock en `sys.modules` para evitar carga de modelos ML.
- **cv2**: Mock en `sys.modules` con valores que pasan filtro de calidad.
- **ESP32**: Emulación por funcionalidad (HTTP + MQTT). Hardware-only documentado en `PRUEBAS_FISICAS.md`.
- **Playwright**: Solo Chromium.

## Estructura de archivos

```
Backend/tests/
├── conftest.py                     # Fixtures: app, client, tokens, mocks, PostgreSQL auto-setup
├── docker-compose.test.yml         # PostgreSQL test efímero (puerto 5433)
├── __init__.py
├── test_encryption.py              # 100% — Cifrado AES de embeddings
├── test_app.py                     # 100% — Health + blueprints
├── test_database.py                # 90%  — Schema + seed + migraciones
├── test_routes_general.py          # 95%/90% — Logs, Turnos, Asignaciones
├── test_routes_auth.py             # 95%  — Login, JWT, roles, enrolamiento
├── test_routes_personas.py         # 92%  — CRUD, consentimiento, olvido
├── test_routes_sync_erp.py         # 90%/95% — Asistencias, Dispositivos, ERP
├── test_routes_facial.py           # 90%  — DeepFace mockeado
├── test_mqtt_handler.py            # 90%  — paho mockeado
└── esp32_emulator/
    ├── test_registro_persona.py
    ├── test_marcaje_asistencia.py
    ├── test_sync_offline.py
    ├── test_identificacion_facial.py
    ├── test_heartbeat_watchdog.py
    ├── test_registro_facial_mqtt.py
    ├── test_maquina_estados.py
    ├── test_enrolamiento.py
    └── test_erp_push.py

Frontend/
├── vitest.config.ts
├── playwright.config.ts
├── __tests__/
│   ├── setup.ts
│   ├── handlers.ts
│   ├── lib/
│   │   ├── api.test.ts
│   │   ├── types.test.ts
│   │   └── auth-context.test.tsx
│   ├── components/
│   │   └── app.test.tsx
│   └── api/
│       └── proxy.test.ts
└── e2e/
    └── dashboard.spec.ts

.github/workflows/
└── test.yml
```

## Cobertura estimada

| Archivo | Líneas | Cubiertas | % |
|---|---|---|---|
| `encryption.py` | 31 | 31 | 100% |
| `app.py` | 46 | 46 | 100% |
| `database.py` | 274 | 247 | 90% |
| `routes/auth.py` | 820 | 770 | 94% |
| `routes/personas.py` | 348 | 320 | 92% |
| `routes/turnos.py` | 94 | 89 | 95% |
| `routes/asignaciones.py` | 126 | 113 | 90% |
| `routes/asistencias.py` | 171 | 154 | 90% |
| `routes/facial.py` | 483 | 435 | 90% |
| `routes/dispositivos.py` | 150 | 138 | 92% |
| `routes/erp.py` | 395 | 375 | 95% |
| `routes/logs.py` | 74 | 74 | 100% |
| `mqtt_handler.py` | 283 | 255 | 90% |
| **Total Backend** | **~3295** | **~3047** | **92%** |
| Frontend unit/comp | ~1250 | ~1100 | 88% |
| Frontend E2E | ~2257 | ~2031 | 90% |
| **Total Frontend** | **~3507** | **~3131** | **89%** |
| **TOTAL GLOBAL** | **~6802** | **~6178** | **91%** |

## Pruebas físicas (hardware)

59 pruebas que requieren ESP32-CAM físico documentadas en `tests/PRUEBAS_FISICAS.md`:
- Iteración 1: Cámara, AS608, PIR, AP (5 pruebas)
- Iteración 2: LittleFS, offline, alternancia (7 pruebas)
- Iteración 3: WiFi, MQTT, heartbeat (5 pruebas)
- Iteración 4: Facial, anti-spoofing, iluminación (9 pruebas)
- Iteración 5: Autenticación multi-tenant (10 pruebas)
- Iteración 6: Antifraude PIR/flash/cooldown (9 pruebas)
- Iteración 7: Panel web, ERP (9 pruebas)
- Iteración 8: Sincronización, logs, watchdog (10 pruebas)

## Cómo ejecutar

### Requisitos previos

| Herramienta | Versión | Verificar |
|---|---|---|
| Python | ≥3.12 | `python --version` |
| Node.js | ≥22 | `node --version` |
| Docker Desktop | Última estable | `docker info` |
| Git | Cualquiera | `git --version` |

### 1. Backend

#### 1.1 Instalar dependencias

```powershell
# Desde la raiz del proyecto
cd Backend

# Crear y activar venv (recomendado)
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell
# o: .\.venv\Scripts\activate.bat  # CMD

# Instalar dependencias de produccion y testing
pip install -r requirements.txt
pip install -r requirements-test.txt
```

#### 1.2 Ejecutar todos los tests

```powershell
# Asegurar que Docker Desktop esta corriendo
docker info

# Ejecutar desde la raiz del proyecto
pytest Backend/tests -v
```

El `conftest.py` automaticamente:
1. Verifica que Docker esta disponible
2. Levanta PostgreSQL 15 en puerto 5433
3. Crea las 14 tablas con `init_db()`
4. Trunca y re-siembra la BD entre cada test
5. Derriba PostgreSQL al finalizar

#### 1.3 Ejecutar tests por categoria

```powershell
# Solo unitarios (sin Docker, sin DB)
pytest Backend/tests/test_encryption.py -v

# Solo integracion (requiere Docker)
pytest Backend/tests/test_database.py -v
pytest Backend/tests/test_routes_auth.py -v

# Solo tests faciales (DeepFace mockeado)
pytest Backend/tests/test_routes_facial.py -v
pytest Backend/tests/test_mqtt_handler.py -v

# Solo emulador ESP32
pytest Backend/tests/esp32_emulator/ -v

# Ejecutar un test especifico
pytest Backend/tests/test_routes_auth.py::TestRoutesAuth::test_login_exitoso_admin -v

# Ejecutar tests que fallaron la ultima vez
pytest Backend/tests --lf

# Detenerse en el primer fallo
pytest Backend/tests -x
```

#### 1.4 Ejecutar con cobertura

```powershell
pytest Backend/tests --cov=Backend --cov=Backend/routes --cov=Backend/mqtt_handler.py --cov-report=term-missing
```

Para un reporte HTML:

```powershell
pytest Backend/tests --cov=Backend --cov-report=html
# Abrir: ./htmlcov/index.html
```

#### 1.5 Sin Docker (tests unitarios puros)

Si no tienes Docker o quieres ejecutar solo los tests que no requieren BD:

```powershell
# encryption es el unico totalmente independiente
pytest Backend/tests/test_encryption.py -v

# El resto de tests usan el fixture 'app' que requiere PostgreSQL.
# Si Docker no esta disponible, pytest saltara automaticamente esos tests.
```

### 2. Frontend

#### 2.1 Instalar dependencias

```powershell
cd Frontend
npm install
```

Las dependencias de testing (`vitest`, `@testing-library/react`, `msw`, etc.) estan en `devDependencies` del `package.json`. `npm install` las instala automaticamente.

#### 2.2 Ejecutar tests unitarios

```powershell
# Todos los tests unitarios
npx vitest run

# Modo watch (recarga al guardar)
npx vitest

# Con cobertura
npx vitest run --coverage

# Un archivo especifico
npx vitest run __tests__/lib/api.test.ts

# UI interactiva de Vitest
npx vitest --ui
```

#### 2.3 Ejecutar tests E2E (Playwright)

```bash
# Instalar navegador chromium (solo primera vez)
npx playwright install chromium

# Ejecutar tests E2E
npx playwright test

# Modo debug (abre navegador visible)
npx playwright test --debug

# Solo un test
npx playwright test dashboard.spec.ts
```

> **Nota**: Playwright levanta `next dev` automaticamente como webserver. Asegurate de tener el puerto 3000 libre.

### 3. Ambos a la vez

```powershell
# Desde la raiz del proyecto, en orden:
cd Backend\tests && pytest -v; if ($?) { cd ..\..\Frontend; npx vitest run }
```

---

## Salida esperada

```
============================= test session starts ==============================
collected 156 items

Backend/tests/test_encryption.py::TestEncryption::test_cifrar_produce_string_valido PASSED [  1%]
Backend/tests/test_app.py::TestApp::test_health_endpoint PASSED              [  2%]
...
Backend/tests/test_routes_facial.py::TestRoutesFacial::test_registrar_con_consentimiento_exitoso PASSED [ 92%]
Backend/tests/esp32_emulator/test_heartbeat_watchdog.py::TestEmuladorHeartbeatWatchdog::test_heartbeat_activa_dispositivo PASSED [ 100%]

============================= 156 passed in 8.53s =============================
```

---

## Problemas comunes

### Docker no arranca

```
Docker no disponible — saltando tests de integracion
```

Solucion: Abre Docker Desktop, espera a que termine de cargar (icono verde). Si no lo tienes, los tests de integracion se saltan.

### PostgreSQL no esta listo

```
PostgreSQL test no arranco en 20s
```

Solucion: Docker puede estar lento la primera vez (bajar imagen `postgres:15`). Reintenta.

### deepface no instalado

Los modelos de DeepFace estan mockeados en `sys.modules` desde `conftest.py`, por lo que **no se carga ningun modelo**. Los tests faciales corren en <1s sin GPU.

### Puerto 5433 en uso

El `docker-compose.test.yml` usa puerto 5433 para el PostgreSQL de test. Si esta ocupado:

```powershell
# Ver quien usa el puerto
netstat -ano | findstr 5433

# Liberar: detener el servicio que lo usa, o cambiar el puerto en:
# - Backend/tests/docker-compose.test.yml (linea ports)
# - Backend/tests/conftest.py (linea TEST_DB_URL)
```

### next dev no arranca (Playwright E2E)

El test E2E de Playwright levanta `next dev` como servidor local. Si falla:

```powershell
# Asegurar que next puede buildear
cd Frontend
npx next build
```

---

## Interpretar resultados de cobertura

```
Name                     Stmts   Miss   Cover    Missing
----------------------------------------------------------------------
Backend\encryption.py       31      0    100%
Backend\app.py              46      0    100%
Backend\routes\auth.py     820     55     93%    230-247, 401-410, 650-670
```

- **Stmts**: lineas de codigo ejecutables
- **Miss**: lineas no cubiertas por ningun test
- **Cover**: porcentaje cubierto
- **Missing**: numeros de linea no cubiertos

Las lineas no cubiertas tipicas corresponden a:
- Bloques `except Exception` que solo se disparan con errores de red
- Codigo legacy de fragmentacion MQTT (`mqtt_handler.py:128-172`)
- Ramas de debug/print que no afectan logica de negocio

---

## Flujo de CI/CD (GitHub Actions)

El workflow en `.github/workflows/test.yml` corre automaticamente en cada push y PR a `main`/`master`:

1. **backend-tests**: Levanta PostgreSQL 15, instala Python, ejecuta `pytest`
2. **frontend-tests**: Instala Node 22, ejecuta `vitest run --coverage`

La cobertura se sube como artefacto. Los resultados aparecen en la pestaña Actions del repositorio.

## Fixtures de conftest.py

| Fixture | Scope | Descripción |
|---|---|---|
| `postgres` | session | Docker PostgreSQL up/down |
| `_schema` | session | init_db() para crear tablas |
| `app` | function | Flask app + DB limpia (truncate + re-seed) |
| `client` | function | Flask test_client |
| `admin_token` | function | JWT admin (admin@empresa.cl / admin123) |
| `empleador_token` | function | JWT empleador empresa 2 |
| `trabajador_token` | function | JWT trabajador empresa 2 |
| `mock_deepface_repr` | function | Mock DeepFace.represent |
| `mock_requests_post` | function | Mock requests.post |
| `mock_requests_get` | function | Mock requests.get |
| `mock_paho_client` | function | Mock paho.mqtt.client.Client |
| `mock_thread` | function | Mock threading.Thread |
| `persona_factory` | function | Factory para crear personas |
