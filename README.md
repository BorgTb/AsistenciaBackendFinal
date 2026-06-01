# Sistema de Asistencia SAS

Sistema de control de asistencia con reconocimiento facial, soporte para dispositivos ESP32-CAM y gestión de turnos, personas y empresas.

## Requisitos

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (incluido con Docker Desktop)
- Git (opcional, para clonar el repositorio)

## Quick Start

```bash
# 1. Clonar o copiar el proyecto
git clone <url-del-repositorio> asistencia
cd asistencia

# 2. Copiar y configurar variables de entorno (opcional)
cp .env.example .env

# 3. Levantar todos los servicios
docker compose up -d

# 4. Verificar que los servicios están corriendo
docker compose ps

# 5. Acceder al sistema
#    Frontend: http://localhost:3000
#    Backend:  http://localhost:5000
#    Health:   http://localhost:5000/health
```

## Credenciales por Defecto

| Email | Contraseña | Rol |
|---|---|---|
| `admin@empresa.cl` | `admin123` | Administrador |

> ⚠️ **Cambia la contraseña y el `JWT_SECRET` en producción.**

## Servicios

| Servicio | Puerto Host | Descripción |
|---|---|---|
| `frontend` | `3000` | Interfaz web Next.js |
| `backend` | `5000` | API Flask + reconocimiento facial |
| `postgres` | `5432` | Base de datos PostgreSQL |
| `mosquitto` | `1884` (MQTT), `9001` (WS) | Broker MQTT para ESP32-CAM |

## Variables de Entorno

Copia `.env.example` a `.env` y ajusta según necesites:

| Variable | Default | Descripción |
|---|---|---|
| `POSTGRES_USER` | `sas` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | `sas123` | Contraseña de PostgreSQL |
| `POSTGRES_DB` | `sas_db` | Nombre de la base de datos |
| `DATABASE_URL` | `postgresql://sas:sas123@postgres:5432/sas_db` | URL completa de conexión a la BD |
| `JWT_SECRET` | `sas-secret-cambiar-en-produccion` | Clave secreta para firmar tokens JWT |
| `FLASK_API_BASE_URL` | `http://backend:5000` | URL del backend (para el frontend) |

## Arquitectura

```
Cliente Web (Navegador)
        │
        ▼
  ┌───────────┐     proxy API     ┌───────────┐     SQL      ┌──────────┐
  │  Frontend  │ ──────────────►  │  Backend   │ ──────────► │ Postgres │
  │  Next.js   │                  │  Flask     │              │   DB     │
  │  :3000     │                  │  :5000     │              │  :5432   │
  └───────────┘                  └───────────┘              └──────────┘
                                       │
                                       │ MQTT
                                       ▼
                                ┌───────────┐
                                │  Mosquitto │ ◄──── ESP32-CAM
                                │  :1884     │
                                └───────────┘
```

## Configuración de Dispositivos ESP32-CAM

Los dispositivos ESP32-CAM se conectan al sistema vía MQTT.

1. Graba el firmware correspondiente en el ESP32 (`esp32-cam/esp32/` o `esp32-cam/esp32-sin-lector/`)
2. Configura la red WiFi y la IP del broker MQTT en el código del dispositivo
3. El broker MQTT corre en `localhost:1884` (mapeado al puerto interno `1883`)
4. Los dispositivos pueden conectarse usando la IP del host donde corre Docker

## Comandos Útiles

```bash
# Ver logs de todos los servicios
docker compose logs -f

# Ver logs de un servicio específico
docker compose logs -f backend

# Reconstruir imágenes después de cambios
docker compose up -d --build

# Detener servicios
docker compose down

# Detener servicios y eliminar volúmenes (borra datos de BD)
docker compose down -v

# Reiniciar un servicio
docker compose restart backend
```

## Solución de Problemas

### El backend no arranca por la base de datos
El backend espera a que PostgreSQL esté listo (health check). Si falla, revisa los logs:
```bash
docker compose logs postgres
```

### DeepFace tarda mucho en el primer inicio
En el primer arranque, DeepFace descarga modelos de reconocimiento facial (~500MB). Esto es normal y solo ocurre una vez (se cachean en el volumen `deepface_models`).

### Error de conexión MQTT
Verifica que Mosquitto esté corriendo:
```bash
docker compose logs mosquitto
```

### El frontend muestra errores de conexión
Asegúrate de que la variable `FLASK_API_BASE_URL` apunte a `http://backend:5000` (nombre del servicio interno de Docker).

## Producción

Para entornos productivos:

1. **Cambia `JWT_SECRET`** por una clave segura
2. **Cambia las contraseñas** por defecto de PostgreSQL y del admin
3. **Configura HTTPS** con un reverse proxy (Nginx, Traefik, Caddy)
4. **Aumenta los límites de recursos** de los contenedores si es necesario
5. **Configura backups** de la base de datos
