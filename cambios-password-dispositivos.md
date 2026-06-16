# Generar contraseñas para ESP32 desde el backend

Plan implementado para que un administrador pueda, desde el panel web (`/dispositivos`), generar una contraseña para un dispositivo, y que el ESP32 la reciba automáticamente y la use como su contraseña de administrador local.

---

## 1. Base de datos

### `Backend/database.py:45-47`

Tres nuevas columnas en `dispositivos`:

| Columna | Tipo | Uso |
|---------|------|-----|
| `password_hash` | `VARCHAR(64)` | SHA-256 hex de la contraseña (persistente) |
| `password_plain` | `VARCHAR(20)` | Contraseña en texto plano (se elimina al confirmar) |
| `password_pendiente` | `BOOLEAN DEFAULT FALSE` | Flag que indica que el ESP32 aún no ha aplicado la contraseña |

```sql
ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS password_hash VARCHAR(64);
ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS password_plain VARCHAR(20);
ALTER TABLE dispositivos ADD COLUMN IF NOT EXISTS password_pendiente BOOLEAN DEFAULT FALSE;
```

---

## 2. Backend — Nuevos endpoints

Todos en `Backend/routes/dispositivos.py`.

### `POST /api/dispositivos/<id>/generar-password`
- **Auth:** admin/empleador
- **Acción:** Genera contraseña aleatoria de 12 chars (letras + dígitos), calcula SHA-256, guarda en DB, retorna la contraseña en texto plano
- **Validación:** Solo para dispositivos enrolados (`enrolado=TRUE` con `mac_address`)

### `GET /api/dispositivos/check-password`
- **Auth:** dispositivo (por header `X-Device-MAC`)
- **Acción:** Retorna `{pendiente: true, password: "..."}` si hay contraseña pendiente, `{pendiente: false}` si no

### `POST /api/dispositivos/confirmar-password`
- **Auth:** dispositivo (por header `X-Device-MAC`)
- **Acción:** Confirma que el ESP32 aplicó la contraseña. Marca `password_pendiente=FALSE`, limpia `password_plain`

### `DELETE /api/dispositivos/<id>/password`
- **Auth:** admin/empleador
- **Acción:** Elimina la contraseña del dispositivo (limpia los 3 campos)

### `GET /api/dispositivos` (modificado)
- Nuevos campos en respuesta JSON: `tiene_password` (bool) y `password_pendiente` (bool)

---

## 3. Frontend

### `Frontend/lib/types.ts`
Agregados a `DeviceStatus`:
- `tienePassword?: boolean`
- `passwordPendiente?: boolean`

### `Frontend/lib/auth-api.ts`
Nuevas funciones:
- `generarPasswordDispositivo(dispositivoId)` → `POST /api/dispositivos/<id>/generar-password`
- `eliminarPasswordDispositivo(dispositivoId)` → `DELETE /api/dispositivos/<id>/password`

### `Frontend/components/SasDashboard.tsx`
- **Indicador visual:** 🔒 (con contraseña), 🔑 (pendiente de aplicar), 🔓 (sin contraseña)
- **Botón "Generar contraseña"** en cada tarjeta de dispositivo
- **Botón "Regenerar contraseña"** si ya tiene (con confirmación de sobrescritura)
- **Botón "Quitar contraseña"** (con confirmación)
- **Modal** que muestra la contraseña generada con advertencia "solo se muestra una vez" y botón Copiar

---

## 4. ESP32 Firmware

### Ambos archivos:
- `esp32-cam-solo-rostro/esp32-cam-solo-rostro.ino`
- `esp32-cam/esp32/esp32.ino`

### Nueva función: `verificarPasswordPendiente()`

```
Cada 60 segundos (si está online):
  1. HTTP GET /api/dispositivos/check-password (con X-Device-MAC)
  2. Si pendiente == true:
     a. adminHash = sha256(password)
     b. saveAdminHash()
     c. HTTP POST /api/dispositivos/confirmar-password
```

### Integración en `loop()`
Timer `lastPwdCheck` cada 60,000ms, ejecuta `verificarPasswordPendiente()`.

### Sin cambios en:
- `requiereAdmin()` — ya funciona con `adminHash`
- `verificarPassword()` — ya compara SHA-256
- `saveAdminHash()` / `cargarAdminHash()` — persisten en `/admin.json`

---

## 5. Flujo completo

```
Admin web                Backend                         ESP32
│                         │                              │
├─ Generar contraseña ───►│                              │
│                         ├── SHA-256(pwd)               │
│                         ├── Guarda hash+plain+pendiente│
│◄─── {password: "Ab3..."} │                              │
│ (se muestra una vez)    │                              │
│                         │                              │
│                    ──── Si online ────────────────────►│
│                         │                    [cada 60s] │
│                         │◄─ GET /check-password ───────┤
│                         ├── pendiente=TRUE             │
│                         ├── password="Ab3..."          │
│                    ────┼──────────────────────────────►│
│                         │                      ├── sha256(pwd)
│                         │                      ├── saveAdminHash()
│                         │                      └── POST /confirmar-password
│                         │◄── Confirmación ─────────────┤
│                         ├── pendiente=FALSE            │
│                         ├── password_plain=NULL        │
│                         │                              │
│                    ──── Si offline ────────────────┐   │
│  Admin accede        │                            │   │
│  manualmente via     │                            │   │
│  WiFi Setup          │                            │   │
│  del ESP32           │                            │   │
│                      └────────────────────────────┼───┤
│                                                   └──►│
│                         │          [vuelve online]     │
│                         │◄── polling detecta mismo hash│
│                         │      Confirma igual          │
│                         │                              │
│  Accede con:           │                              │
│  ?admin_password=Ab3.. │                              │
│  ────────────────────────────────────────────────────►│
│                         │                      ├── verificarPassword() ✓
```

---

## 6. Consideraciones de seguridad

- La contraseña viaja en texto plano por HTTP (igual que el resto del sistema). En producción usar HTTPS.
- `password_plain` se almacena temporalmente en DB y se elimina tras confirmación.
- La contraseña se muestra **una sola vez** al admin.
- SHA-256 del backend (`hashlib`) coincide con `mbedtls SHA-256` del ESP32.
- Si el dispositivo está offline, la contraseña queda pendiente hasta que conecte.
- El admin puede opcionalmente ingresar la contraseña manualmente en WiFi Setup.

---

## 7. Archivos modificados

| Archivo | Cambios |
|---------|---------|
| `Backend/database.py` | +3 ALTER TABLE (línea 45-47) |
| `Backend/routes/dispositivos.py` | Imports, SELECTs actualizados, +4 endpoints nuevos |
| `Frontend/lib/types.ts` | +2 campos en `DeviceStatus` |
| `Frontend/lib/api.ts` | Campos `getDispositivos()` actualizados |
| `Frontend/lib/auth-api.ts` | +2 funciones |
| `Frontend/components/SasDashboard.tsx` | States, handlers, UI indicador + modal |
| `esp32-cam-solo-rostro/esp32-cam-solo-rostro.ino` | +`verificarPasswordPendiente()` + timer en `loop()` |
| `esp32-cam/esp32/esp32.ino` | +`verificarPasswordPendiente()` + timer en `loop()` |
