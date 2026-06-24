# Testing del Modo Seguro — Paso a Paso

## Requisitos

- Docker Desktop instalado y funcionando
- Proyecto clonado y en la rama correcta

---

## Paso 1: Generar certificados

Abrir **PowerShell** y ejecutar:

```powershell
.\Backend\certs\generate_certs.ps1
```

Esto crea los archivos en `Backend/certs/` (ca.crt, server.crt, server.key, client.crt, client.key)
y el archivo `Backend/mosquitto/config/passwd` con usuario `sas` / contraseña `sas123`.

> Si el script falla, asegúrate de que Docker Desktop esté funcionando (`docker ps`).

---

## Paso 2: Probar modo NO SEGURO (comportamiento actual)

```powershell
# 1. Asegurar que la variable no está seteada
Remove-Item Env:SECURE_MODE -ErrorAction SilentlyContinue

# 2. Levantar servicios
docker compose up -d

# 3. Verificar health HTTP
curl http://localhost:5000/health

# 4. Revisar logs del backend
docker logs sas_backend
```

**Esperado:**
- `curl` devuelve `{"status":"ok","version":"1.0"}`
- Logs muestran: `🔓 Modo NO SEGURO: conectando MQTT a mosquitto:1883`

```powershell
# 5. Bajar servicios
docker compose down
```

---

## Paso 3: Probar modo SEGURO

```powershell
# 1. Setear variables
$env:SECURE_MODE = "true"
$env:MQTT_PASSWORD = "sas123"

# 2. Levantar servicios
docker compose up -d

# 3. Verificar HTTPS (cert autofirmado, usar -k o --skip-certificate)
curl -k https://localhost:443/health

# 4. Verificar que HTTP sigue funcionando (puerto 5000 siempre activo)
curl http://localhost:5000/health

# 5. Revisar logs del backend
docker logs sas_backend
```

**Esperado:**
- Ambos curls devuelven `{"status":"ok","version":"1.0"}`
- Logs muestran: `🔒 Modo SEGURO: conectando MQTT con TLS a mosquitto:8883`
- Logs muestran: `🔒 HTTPS en puerto 443 (cert=/app/certs/server.crt)`

---

## Paso 4: Verificar que MQTT plano está bloqueado en modo seguro

```powershell
# Intentar conectar sin TLS al puerto seguro — debe fallar
docker run --rm eclipse-mosquitto mosquitto_sub -h localhost -p 8884 -t "esp32/#" -v
```

**Esperado:** Error de conexión (connection refused o connection reset).

---

## Paso 5: Verificar que MQTT con TLS funciona

```powershell
docker run --rm `
  -v "${PWD}\Backend\certs:/certs:ro" `
  eclipse-mosquitto mosquitto_sub `
  -h localhost -p 8884 `
  --cafile /certs/ca.crt `
  -u sas -P sas123 `
  -t "esp32/heartbeat/#" `
  -v
```

**Esperado:** Se ven heartbeats de los dispositivos conectados (o al menos ningún error de TLS).

---

## Paso 6: Alternar entre modos (persistencia de datos)

```powershell
# 1. Iniciar en modo no seguro
$env:SECURE_MODE = "false"
docker compose up -d
# (opcional) Crear datos de prueba vía API
curl -X POST http://localhost:5000/api/personas -H "Content-Type: application/json" -d "{...}"
docker compose down

# 2. Iniciar en modo seguro
$env:SECURE_MODE = "true"
$env:MQTT_PASSWORD = "sas123"
docker compose up -d

# 3. Verificar que datos persisten
curl -k https://localhost:443/api/personas

docker compose down
```

**Esperado:** Los datos creados en modo no seguro aparecen en modo seguro.
(PostgreSQL usa volumen persistente `postgres_data`).

---

## Paso 7: Ejecutar tests unitarios

```powershell
# Activar virtual env
cd Backend
.venv\Scripts\python -m pytest tests/test_mqtt_handler.py -v
```

**Esperado:** Todos los tests pasan.

---

## Paso 8: Resumen de validación visual

```powershell
# Script rápido para verificar estado actual
Write-Host "=== CHECK ===" -ForegroundColor Cyan

$http = $false; $https = $false
try { $r = Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing; $http = $r.StatusCode -eq 200 } catch {}
try { $r = Invoke-WebRequest -Uri "https://localhost:443/health" -SkipCertificateCheck -UseBasicParsing; $https = $r.StatusCode -eq 200 } catch {}

if ($http) { Write-Host "  HTTP : OK" -ForegroundColor Green } else { Write-Host "  HTTP : FAIL" -ForegroundColor Red }
if ($https) { Write-Host "  HTTPS: OK" -ForegroundColor Green } else { Write-Host "  HTTPS: FAIL" -ForegroundColor Red }

$logs = docker logs sas_backend 2>&1
if ($logs -match "Modo SEGURO") { Write-Host "  MQTT : SEGURO" -ForegroundColor Green }
elseif ($logs -match "Modo NO SEGURO") { Write-Host "  MQTT : NO SEGURO" -ForegroundColor Yellow }
else { Write-Host "  MQTT : SIN CONEXION" -ForegroundColor Red }
```

---

## Referencia: Comandos útiles

```powershell
# Ver logs del backend en tiempo real
docker logs -f sas_backend

# Ver logs de mosquitto
docker logs sas_mosquitto

# Verificar que los puertos están expuestos
docker compose ps

# Forzar reconstrucción del backend
docker compose build backend
docker compose up -d
```
