# Seguridad del Sistema SAS

## 1. Arquitectura de Seguridad

```
┌─────────────────────────────────────────────────────────┐
│                   INTERNET (no confiable)                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ESP32 ──wss:// (TLS 1.3) ──→ Cloudflare ──ws://──→   │
│   App Web ──https:// (TLS) ───→ Cloudflare ──http://──→ │
│                                                         │
└─────────────────────────────────────────────────────────┘
                            │
                    ┌───────┴───────┐
                    │   localhost   │  (red interna)
                    ├───────────────┤
                    │  Mosquitto    │
                    │  :1883 (plano)│
                    │  :8883 (TLS)  │
                    │  :9001 (WS)   │
                    └───────┬───────┘
                            │
                    ┌───────┴───────┐
                    │   Backend     │
                    │  Flask/Python │
                    └───────┬───────┘
                            │
                    ┌───────┴───────┐
                    │  PostgreSQL   │
                    └───────────────┘
```

## 2. Capas de Seguridad

### Capa 1: Cifrado en Tránsito (TLS)

| Componente | Canal | Cifrado | Certificado |
|------------|-------|---------|-------------|
| ESP32 → Cloudflare | `wss://` | TLS 1.3 (AES-256-GCM) | Válido (Cloudflare) |
| App Web → Cloudflare | `https://` | TLS 1.3 | Válido (Cloudflare) |
| Backend → Mosquitto (local) | `mqtts://` o `ws://localhost` | TLS 1.3 o loopback | Autofirmado o ninguno |
| Cloudflare → Servicios | `ws://localhost` o `http://localhost` | Sin cifrado | Loopback, no sale al exterior |

**¿Qué protege?** Que nadie en Internet pueda leer ni modificar los datos en tránsito (imágenes faciales, coordenadas de huellas, datos biométricos).

### Capa 2: Autenticación MQTT

- Usuario y contraseña (`sas` / `sas123` o la configurada)
- Se envían dentro del túnel TLS cifrado
- El broker rechaza conexiones sin credenciales en puertos seguros
- El puerto 1883 (plano, sin auth) existe solo para compatibilidad con dispositivos antiguos

**¿Qué protege?** Que solo dispositivos autorizados puedan publicar/consumir mensajes en el bus MQTT.

### Capa 3: Autenticación API (JWT)

- Tokens JWT con expiración de 24 horas
- Roles: `admin` (global), `empleador` (por empresa), `trabajador` (individual)
- Contraseñas hasheadas con bcrypt
- Las rutas sensibles requieren autenticación y rol específico

**¿Qué protege?** Que solo usuarios legítimos puedan acceder a la API.

### Capa 4: Datos Biométricos Cifrados

- Los embeddings faciales se cifran con **Fernet (AES-256)** antes de almacenar en PostgreSQL
- La clave biométrica (`BIOMETRIC_KEY`) está separada de la JWT
- Consentimiento obligatorio antes del registro biométrico

**¿Qué protege?** Que aunque la base de datos sea comprometida, los datos biométricos no son legibles.

## 3. Toggle `SECURE_MODE`

El sistema permite alternar entre **modo no seguro** (desarrollo) y **modo seguro** (producción) con una variable de entorno:

```env
SECURE_MODE=true          # Activa TLS + autenticación
SECURE_MODE=false         # Modo plano (desarrollo local)
```

### Qué cambia según el modo:

| Componente | `SECURE_MODE=false` | `SECURE_MODE=true` |
|------------|--------------------|--------------------|
| API Backend | `http://:5000` | `https://:443` + `http://:5000` |
| Backend → Mosquitto | `mqtt://:1883` (plano) | `mqtts://:8883` (TLS + pass) |
| ESP32 → Mosquitto | `ws://:9001` (plano) | `wss://:9001` (TLS + pass) |
| Usuarios/roles | No aplica | Siempre activo (JWT) |
| Biométricos | Cifrados siempre | Cifrados siempre |
| Contraseñas | Hasheadas siempre | Hasheadas siempre |

## 4. Cómo un desarrollador independiente puede levantar el sistema seguro

### Requisitos

- Docker Desktop
- Un dominio apuntando a Cloudflare (opcional, pero recomendado)
- Cloudflare Tunnel (cloudflared)

### Paso 1: Clonar y generar certificados

```powershell
git clone <repo>
cd AsistenciaBackendFinal
.\Backend\certs\generate_certs.ps1
```

### Paso 2 (alternativa): VPS + dominio propio (sin Cloudflare)

Si tenés un **VPS con dominio** y querés seguridad sin depender de Cloudflare:

```bash
# 1. Obtener certificados Let's Encrypt (reales, no autofirmados)
sudo apt install certbot
sudo certbot certonly --standalone -d mqtt.tu-dominio.com -d api.tu-dominio.com

# 2. Copiar certs a las rutas del proyecto
sudo cp /etc/letsencrypt/live/tu-dominio.com/fullchain.pem Backend/certs/server.crt
sudo cp /etc/letsencrypt/live/tu-dominio.com/privkey.pem   Backend/certs/server.key
sudo cp /etc/letsencrypt/live/tu-dominio.com/chain.pem     Backend/certs/ca.crt

# 3. Configurar Nginx como reverse proxy HTTPS para la API
cat > /etc/nginx/sites-available/sas-api << 'EOF'
server {
    listen 443 ssl;
    server_name api.tu-dominio.com;

    ssl_certificate     /etc/letsencrypt/live/tu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tu-dominio.com/privkey.pem;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF
sudo ln -s /etc/nginx/sites-available/sas-api /etc/nginx/sites-enabled/
sudo nginx -s reload

# 4. Configurar Nginx para WebSocket MQTT (proxy hacia Mosquitto :9001)
cat > /etc/nginx/sites-available/sas-mqtt << 'EOF'
server {
    listen 443 ssl;
    server_name mqtt.tu-dominio.com;

    ssl_certificate     /etc/letsencrypt/live/tu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tu-dominio.com/privkey.pem;

    location /mqtt {
        proxy_pass http://localhost:9001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
sudo ln -s /etc/nginx/sites-available/sas-mqtt /etc/nginx/sites-enabled/
sudo nginx -s reload

# 5. Configurar Mosquitto con los mismos certs de Let's Encrypt
#    (editar Backend/mosquitto/config/mosquitto.conf)
#    Reemplazar las rutas de los certs:
#      cafile    /etc/letsencrypt/live/tu-dominio.com/chain.pem
#      certfile  /etc/letsencrypt/live/tu-dominio.com/fullchain.pem
#      keyfile   /etc/letsencrypt/live/tu-dominio.com/privkey.pem
```

**Ventajas de este enfoque:**

- ✅ Certificados reales de Let's Encrypt (auto renovables)
- ✅ Sin dependencia de terceros (Cloudflare)
- ✅ El ESP32 usa `esp_crt_bundle_attach` y verifica contra Let's Encrypt (CA público)
- ✅ Control total de puertos, logs, firewalls
- ✅ Escalable: podés agregar más instancias detrás de Nginx

**El ESP32 se configura igual**, solo cambian los dominios:

| Campo | Valor |
|-------|-------|
| URL Servidor | `https://api.tu-dominio.com` |
| MQTT Broker | `wss://mqtt.tu-dominio.com` |
| Modo Seguro | ☑ Activado |

```powershell
# Instalar cloudflared
winget install cloudflare.cloudflared

# Autenticar
cloudflared tunnel login

# Crear túnel
cloudflared tunnel create sas-tunnel

# Configurar en ~/.cloudflared/config.yml
tunnel: sas-tunnel
credentials-file: C:\Users\tu-usuario\.cloudflared\sas-tunnel.json
ingress:
  - hostname: mqtt.tu-dominio.com
    service: http://localhost:9001
  - hostname: api.tu-dominio.com
    service: http://localhost:5000
  - service: http_status:404

# Iniciar
cloudflared tunnel run sas-tunnel
```

### Paso 3: Configurar DNS en Cloudflare

```
mqtt.tu-dominio.com  → CNAME  → sas-tunnel.trycloudflare.com
api.tu-dominio.com   → CNAME  → sas-tunnel.trycloudflare.com
```

### Paso 4: Levantar servicios

```powershell
# Opción A: Solo Mosquitto (recomendado para desarrollo)
docker compose up -d mosquitto postgres

# Backend local
cd Backend
.venv\Scripts\python app.py

# Opción B: Todo en Docker (producción)
$env:SECURE_MODE="true"
$env:MQTT_PASSWORD="sas123"
docker compose up -d
```

### Paso 5: Configurar ESP32

1. Conectarse al WiFi del ESP32 (`ESP32-ASISTENCIA` / `Asistencia2026`)
2. Ir a `http://192.168.4.1/wifi-setup`
3. Configurar:

| Campo | Valor |
|-------|-------|
| URL Servidor | `https://api.tu-dominio.com` |
| MQTT Broker | `wss://mqtt.tu-dominio.com` |
| Modo Seguro | ☑ Activado |
| Usuario MQTT | `sas` |
| Contraseña MQTT | `sas123` |

4. Guardar y reiniciar

## 5. Verificación de Seguridad

### Checklist para producción

- [ ] Cloudflare Tunnel activo y funcionando
- [ ] `SECURE_MODE=true` en el entorno
- [ ] Contraseñas cambiadas (JWT, MQTT, Biométrica)
- [ ] Certificados SSL reales (no autofirmados)
- [ ] Puerto 1883 deshabilitado o bloqueado por firewall
- [ ] Base de datos no expuesta públicamente
- [ ] Logs de acceso monitoreados

### Comandos de verificación

```powershell
# Verificar que el backend solo acepta HTTPS desde afuera
curl -k https://api.tu-dominio.com/health
curl http://api.tu-dominio.com:5000/health   # debe fallar

# Verificar que MQTT requiere auth
mosquitto_sub -h mqtt.tu-dominio.com -p 443 -t "esp32/#"
# debe dar error de conexión

# Verificar canal cifrado en logs de Mosquitto
docker logs sas_mosquitto | Select-String "TLSv1.3"
```

## 7. Comparativa: Cloudflare vs VPS directo

| Aspecto | Cloudflare Tunnel | VPS + Nginx + Let's Encrypt |
|---------|------------------|------------------------------|
| Certificados | Automáticos (Cloudflare edge) | Let's Encrypt (gratis, auto renovable) |
| Configuración | Mínima (cloudflared) | Media (Nginx + certbot) |
| Dependencia externa | Sí (Cloudflare) | No (solo tu VPS) |
| Renovación certs | Automática | `certbot renew` o systemd timer |
| Firewall | Cloudflare WAF | Podés usar iptables/ufw |
| Latencia | +1 hop (Cloudflare) | Directo al VPS |
| WebSocket MQTT | Proxy automático | Config manual en Nginx |
| Costo | Gratis (plan Free) | Solo VPS |
| Privacidad | Cloudflare ve el tráfico | Nadie intermedio |

**Recomendación:** Cloudflare para empezar rápido y gratis. VPS directo cuando necesités control total o estés en un país con restricciones de Cloudflare.

| Amenaza | Mitigación | Nivel |
|---------|-----------|-------|
| Interceptación de datos en tránsito | TLS 1.3 entre ESP32/Web → Cloudflare | ✅ Alto |
| Acceso no autorizado al broker MQTT | Autenticación usuario/contraseña en puertos seguros | ✅ Alto |
| Acceso no autorizado a la API | JWT con roles y expiración | ✅ Alto |
| Robo de base de datos | Embeddings cifrados con AES-256 (Fernet) | ✅ Alto |
| Suplantación de dispositivo | X-Device-MAC + PIN de enrolamiento | ✅ Medio |
| Ataque MITM local (misma red) | Solo si usás modo seguro con TLS | ✅ Alto |
| Fuga de datos por puerto abierto | 1883 y 9001 solo accesibles desde localhost en prod | ⚠️ Medio |
