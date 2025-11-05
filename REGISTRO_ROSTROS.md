# 📝 Sistema de Registro de Rostros

## 🎯 Flujo Completo

### **1. Interfaz ESP32**

#### **Inicio (http://[IP_ESP32]/)**
```
┌─────────────────────────────┐
│   📷 Sistema Asistencia     │
│  Estado: WiFi/MQTT/Cámara  │
└─────────────────────────────┘
│
├─── 🎯 RECONOCIMIENTO
│    ├─ 🎥 Reconocer Rostro
│    └─ 📸 Foto
│
├─── 👤 REGISTRO
│    └─ ✏️ Registrar Persona
│
└─── ⚙️ CONFIGURACIÓN
     ├─ 🎥 Ver Video
     └─ 🌐 WiFi
```

---

## 📱 Flujo de Reconocimiento

### **Paso 1: Acceder a reconocimiento**
```
1. Abrir: http://[IP_ESP32]/
2. Click: "🎥 Reconocer Rostro"
```

### **Paso 2: Ver video en vivo**
```
- Se muestra stream MJPEG en tiempo real
- Puedes preparar la foto
```

### **Paso 3: Capturar y reconocer**
```
1. Click: "✅ Reconocer"
2. ESP32 captura imagen
3. Envía por MQTT a Python
4. Python reconoce el rostro
5. Resultado en asistencia.csv
```

### **Resultado**
```
✅ Rostro reconocido: Juan (92.5% confianza)
❌ Rostro desconocido
```

---

## 👤 Flujo de Registro

### **Paso 1: Acceder a registro**
```
1. Abrir: http://[IP_ESP32]/
2. Click: "✏️ Registrar Persona"
```

### **Paso 2: Ver video y preparar foto**
```
- Se muestra stream MJPEG
- Prepara el rostro para captura
```

### **Paso 3: Ingresar nombre y registrar**
```
1. Escribe nombre de la persona (ej: "Juan")
2. Click: "✅ Registrar"
3. ESP32 captura imagen
4. Envía por MQTT con tópico: test/registro/Juan/start|part|end
5. Python guarda la imagen en carpeta rostros/
6. Python agrega encoding a memoria
```

### **Resultado**
```
✅ Rostro registrado: Juan (Juan_20251105_151230.jpg)
```

---

## 📊 Tópicos MQTT

### **Reconocimiento**
```
test/imagenes/{sessionId}/start     → Inicio de transmisión
test/imagenes/{sessionId}/part      → Fragmentos de imagen (base64)
test/imagenes/{sessionId}/end       → Fin de transmisión
```

### **Registro**
```
test/registro/{personName}/start    → Inicio de registro
test/registro/{personName}/part     → Fragmentos de imagen (base64)
test/registro/{personName}/end      → Fin de registro
```

### **Resultado**
```
test/reconocimiento/resultado       → Respuesta del reconocimiento
```

---

## 📁 Estructura de Carpetas

```
Backend:
├── rostros/                    # Rostros conocidos (para reconocimiento)
│   ├── Juan_20251105_100000.jpg
│   ├── Maria_20251105_100100.jpg
│   └── ...
│
├── imagenes/                   # Imágenes procesadas (temporal)
│   ├── imagen_0.jpg
│   ├── imagen_1.jpg
│   └── ...
│
├── asistencia.csv             # Log de asistencias
│   └── 2025-11-05 15:00:00, Juan, 92.5%
│
└── debug.log                  # Logs de depuración
```

---

## 🔄 Proceso Python (Backend)

### **En app.py**

#### **1. Recibe por MQTT:**
```python
# test/imagenes/{sessionId}/start|part|end
# ↓
# Python arma buffer
# ↓
# Decodifica base64 → imagen JPEG
# ↓
# Guarda en imagenes/imagen_X.jpg
```

#### **2. Reconocimiento:**
```python
recognize_face(imagen_X.jpg)
├─ Carga imagen
├─ Detecta rostros
├─ Compara con known_encodings
├─ Si encuentra coincidencia:
│   ├─ Escribe en asistencia.csv
│   └─ Registra confianza
└─ Si no encuentra:
   └─ Registra como "desconocido"
```

#### **3. Registro:**
```python
register_face(imagen_X.jpg, "Juan")
├─ Carga imagen
├─ Detecta rostros
├─ Si hay rostro:
│   ├─ Copia imagen a rostros/Juan_timestamp.jpg
│   ├─ Genera encoding
│   ├─ Agrega a known_encodings[]
│   ├─ Agrega a known_names[]
│   └─ ✅ Listo para reconocer
└─ Si no hay rostro:
   └─ ❌ Error: sin rostros detectados
```

---

## ✅ Checklist de Configuración

- [ ] **ESP32-CAM:**
  - [ ] Compilar y subir código
  - [ ] Conectar a WiFi
  - [ ] Verificar MQTT conectado
  - [ ] Verificar cámara iniciada

- [ ] **Python Backend:**
  - [ ] Carpeta `rostros/` vacía o con rostros conocidos
  - [ ] Docker ejecutándose: `docker-compose up`
  - [ ] Verificar logs: `docker exec reconocimiento_facial tail -f /app/debug.log`

- [ ] **Primer uso:**
  - [ ] Registrar 3-5 personas
  - [ ] Probar reconocimiento
  - [ ] Verificar asistencia.csv

---

## 🐛 Troubleshooting

### **"❌ WiFi no conectado"**
- [ ] Ir a http://[IP_ESP32]/wifi
- [ ] Ingresar credenciales WiFi
- [ ] Guardar y reiniciar

### **"❌ MQTT no conectado"**
- [ ] Verificar IP MQTT en código: `192.168.1.2`
- [ ] Verificar Mosquitto en Docker: `docker ps`
- [ ] Reconectar ESP32

### **"⚠️ No se detectó rostro"**
- [ ] Acercarse más a la cámara
- [ ] Mejor iluminación
- [ ] Posición frontal del rostro

### **"❌ Rostro desconocido"**
- [ ] Primero registrar la persona
- [ ] Calidad de foto para registro debe ser buena
- [ ] Posición similar entre registro y reconocimiento

---

## 📊 CSV de Asistencia

Formato:
```csv
timestamp, nombre, confianza
2025-11-05 15:00:00.123456, Juan, 92.5%
2025-11-05 15:01:15.654321, Maria, 88.3%
2025-11-05 15:02:30.789012, Desconocido, N/A
```

---

## 🚀 Comandos Útiles

### **Ver logs en tiempo real:**
```bash
docker exec reconocimiento_facial tail -f /app/debug.log
```

### **Ver rostros registrados:**
```bash
ls -la rostros/
```

### **Limpiar asistencia:**
```bash
rm asistencia.csv  # O borrarlo desde Docker
```

### **Listar mensajes MQTT:**
```bash
docker exec mosquitto mosquitto_sub -t "test/#" -v
```

---

## 📞 Conexión de Componentes

```
ESP32-CAM (WiFi) → Mosquitto (1883) → Python Backend
                        ↓
                    Docker Container
                        ↓
                    Procesamiento
                    de Rostros
                        ↓
                    asistencia.csv
```

