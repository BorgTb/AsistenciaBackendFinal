# 🔄 Sistema Integrado ESP32-CAM ↔ Backend

## 🎯 Características del Sistema Integrado

### ✅ Control Bidireccional Completo

**Desde el ESP32-CAM puedes:**
- 📷 Registrar rostros
- 👥 Ver lista de personas registradas
- 🕐 Ver turnos disponibles
- ➕ Asignar turnos a personas
- 🔍 Activar/Desactivar detección automática

**Desde test_api.html puedes:**
- 📱 Ver todos los dispositivos ESP32 registrados
- 🎮 Controlar dispositivos remotamente
- 🔍 Activar/Desactivar detección automática de cualquier ESP32
- 📊 Consultar estado de dispositivos
- ➕ Registrar nuevos dispositivos

## 🚀 Cómo Usar

### 1️⃣ **Interfaz Web del ESP32-CAM**

Accede a la IP de tu ESP32-CAM en el navegador (ejemplo: `http://192.168.1.100`)

**Verás 4 pestañas:**

#### 📝 **Pestaña Registro**
- Ingresar nombre de la persona
- Clic en "📷 Registrar Rostro" para capturar
- Botón "🔍 Detección Auto" para activar/desactivar escaneo continuo
- Ver respuestas del servidor en tiempo real

#### 👥 **Pestaña Personas**
- Ver lista completa de personas registradas
- Muestra: nombre, fecha de registro, cantidad de fotos
- Botón "🔄 Actualizar" para refrescar

#### 🕐 **Pestaña Turnos**
- Ver todos los turnos disponibles
- Muestra: nombre del turno, horario, días de la semana
- Botón "🔄 Actualizar" para refrescar

#### ➕ **Pestaña Asignar**
- Seleccionar persona del dropdown
- Seleccionar turno del dropdown
- Clic en "✅ Asignar Turno"
- Ver confirmación de asignación

### 2️⃣ **Interfaz Web del Backend (test_api.html)**

Abre `test_api.html` en tu navegador

**Ahora incluye 5 pestañas (nueva pestaña: Dispositivos)**

#### 📱 **Pestaña Dispositivos (NUEVA)**

**Ver Dispositivos Registrados:**
- Tabla con: ID, Nombre, IP, Estado, Detección Auto, Última Conexión
- Botón "🔄 Actualizar" para refrescar lista

**Registrar Nuevo Dispositivo:**
- Clic en "➕ Registrar Nuevo"
- Ingresar IP del ESP32 (ej: 192.168.1.100)
- Ingresar nombre descriptivo (ej: "ESP32-CAM Entrada")

**Control Remoto:**
- Clic en "🎮 Controlar" en cualquier dispositivo
- Aparece panel de control remoto
- Botones disponibles:
  - **🔍 Toggle Detección Auto**: Activa/desactiva desde el backend
  - **📊 Ver Estado**: Consulta el estado actual del dispositivo

## 🔧 Configuración Inicial

### **Paso 1: Configurar IP del Backend en ESP32**

En el archivo `codio.ino`, línea ~33:

```cpp
const char* api_server = "http://192.168.1.2:5000/api"; // Cambiar por tu IP
```

**⚠️ IMPORTANTE:** Cambiar `192.168.1.2` por la IP de tu computadora donde corre Docker.

### **Paso 2: Configurar IP del Backend en test_api.html**

En `test_api.html`, dentro del JavaScript (línea ~369 en ESP32 HTML):

```javascript
const API='http://192.168.1.2:5000/api'; // Cambiar por tu IP
```

### **Paso 3: Iniciar Servicios**

```bash
# Reconstruir con nuevas dependencias
docker-compose down
docker-compose up -d --build

# Verificar logs
docker-compose logs -f reconocimiento
```

### **Paso 4: Subir Código al ESP32**

1. Abrir `codio.ino` en Arduino IDE
2. Instalar librería: **ArduinoJson** (buscar en Library Manager)
3. Verificar que HTTPClient esté disponible (viene con ESP32 core)
4. Compilar y subir al ESP32-CAM

### **Paso 5: Registrar el Dispositivo**

**Opción A: Desde test_api.html**
1. Ir a pestaña "📱 Dispositivos"
2. Clic en "➕ Registrar Nuevo"
3. Ingresar IP del ESP32
4. Ingresar nombre

**Opción B: El dispositivo se registra automáticamente** cuando envía la primera imagen.

## 📡 Flujo de Comunicación

### **Registro de Rostro desde ESP32:**
```
1. Usuario ingresa nombre en ESP32
2. ESP32 captura foto
3. ESP32 → MQTT → Backend (envía imagen)
4. Backend detecta rostro
5. Backend guarda en CSV y /imagenes
6. Backend → MQTT → ESP32 (respuesta)
7. ESP32 muestra resultado en pantalla
```

### **Control Remoto desde Backend:**
```
1. Usuario selecciona ESP32 en test_api.html
2. Clic en "Toggle Detección Auto"
3. Backend → HTTP → ESP32 (endpoint /auto-detect)
4. ESP32 cambia estado
5. ESP32 → HTTP → Backend (respuesta)
6. Backend muestra confirmación
7. Backend actualiza CSV de dispositivos
```

### **Consulta desde ESP32:**
```
1. Usuario abre pestaña "Personas" en ESP32
2. ESP32 → HTTP → Backend (GET /api/personas)
3. Backend → HTTP → ESP32 (JSON con lista)
4. ESP32 muestra tabla en navegador
```

## 🌐 Endpoints del ESP32

El ESP32-CAM expone estos endpoints HTTP:

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/` | GET | Página principal con interfaz |
| `/register?nombre=X` | GET | Registrar rostro con nombre |
| `/auto-detect` | GET | Toggle detección automática |
| `/status` | GET | Obtener estado actual |
| `/capture` | GET | Capturar y enviar imagen MQTT |

## 🔄 Endpoints del Backend para ESP32

Nuevos endpoints agregados:

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/dispositivos` | GET | Lista todos los dispositivos |
| `/api/dispositivos/:id` | GET | Obtiene info de dispositivo |
| `/api/dispositivos/register` | POST | Registra nuevo dispositivo |
| `/api/dispositivos/control` | POST | Controla dispositivo remoto |

### **Ejemplo de Control Remoto:**

```bash
# Activar detección automática en ESP32
curl -X POST http://localhost:5000/api/dispositivos/control \
  -H "Content-Type: application/json" \
  -d '{
    "ip": "192.168.1.100",
    "accion": "auto-detect"
  }'
```

```bash
# Consultar estado del ESP32
curl -X POST http://localhost:5000/api/dispositivos/control \
  -H "Content-Type: application/json" \
  -d '{
    "ip": "192.168.1.100",
    "accion": "status"
  }'
```

```bash
# Registrar rostro remotamente
curl -X POST http://localhost:5000/api/dispositivos/control \
  -H "Content-Type: application/json" \
  -d '{
    "ip": "192.168.1.100",
    "accion": "registro",
    "parametros": {
      "nombre": "Juan Perez"
    }
  }'
```

## 📊 Archivo CSV de Dispositivos

**dispositivos.csv:**
```csv
id,nombre,ip,estado,deteccion_auto,ultima_conexion
1,ESP32-CAM Entrada,192.168.1.100,online,true,2024-11-12 10:30:00
2,ESP32-CAM Salida,192.168.1.101,online,false,2024-11-12 10:25:00
```

## 🎨 Interfaz ESP32-CAM

### **Diseño Optimizado:**
- ✅ CSS minificado (ocupa menos memoria)
- ✅ JavaScript compacto
- ✅ Carga dinámica de datos (no almacena todo en memoria)
- ✅ Responsive design
- ✅ Pestañas sin recargar página

### **Colores y Estilo:**
- Fondo: Gradiente morado/azul
- Botones primarios: Gradiente morado
- Botones de acción: Verde
- Estados: Gris claro
- Alertas: Amarillo/Rojo/Verde según contexto

## 🔧 Solución de Problemas

### **ESP32 no se conecta a la API:**
1. Verificar IP en `codio.ino`
2. Verificar que el backend esté corriendo: `curl http://localhost:5000/api/health`
3. Verificar que ESP32 y PC estén en la misma red
4. Ver logs del ESP32 en Serial Monitor

### **test_api.html no puede controlar ESP32:**
1. Verificar IP del ESP32 en la tabla
2. Verificar que el ESP32 esté encendido
3. Intentar acceder manualmente: `http://[IP_ESP32]/status`
4. Verificar CORS del backend

### **ESP32 no muestra personas/turnos:**
1. Verificar que el backend tenga datos: `curl http://localhost:5000/api/personas`
2. Ver consola del navegador (F12) para errores
3. Verificar IP del API en código JavaScript del ESP32

### **Dispositivo no aparece en lista:**
1. Registrarlo manualmente desde test_api.html
2. O esperar a que envíe su primera imagen (se registra automáticamente)
3. Verificar archivo `data/dispositivos.csv`

## 🚀 Características Avanzadas

### **Multi-Dispositivo:**
- Puedes tener múltiples ESP32-CAM
- Todos se registran automáticamente
- Control centralizado desde test_api.html
- Cada uno con su propio estado de detección

### **Persistencia:**
- Todos los dispositivos se guardan en CSV
- Se mantiene el historial de última conexión
- Estado de detección automática por dispositivo

### **Monitoreo:**
- Ver cuándo fue la última vez que un dispositivo se conectó
- Ver estado online/offline
- Ver si tiene detección automática activa

## 📝 Checklist de Implementación

- [ ] Actualizar IP del backend en `codio.ino`
- [ ] Actualizar IP del backend en HTML del ESP32 (línea 369)
- [ ] Instalar librería ArduinoJson en Arduino IDE
- [ ] Subir código actualizado al ESP32
- [ ] Reconstruir contenedores Docker: `docker-compose up -d --build`
- [ ] Verificar que el backend responda: `curl http://localhost:5000/api/health`
- [ ] Acceder a IP del ESP32 en navegador
- [ ] Probar registro de rostro desde ESP32
- [ ] Abrir test_api.html y verificar pestaña Dispositivos
- [ ] Registrar el ESP32 manualmente o esperar auto-registro
- [ ] Probar control remoto desde test_api.html
- [ ] Probar asignación de turnos desde ESP32

## 🎉 Resultado Final

**Sistema completamente integrado donde:**
- ✅ ESP32-CAM funciona como terminal autónoma
- ✅ Backend controla múltiples ESP32 remotamente
- ✅ Datos sincronizados en tiempo real
- ✅ Interfaz dual (ESP32 + Web)
- ✅ Control bidireccional completo
- ✅ Gestión centralizada de dispositivos

---

**¡Sistema listo para producción!** 🚀
