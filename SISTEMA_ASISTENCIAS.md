# 📊 Sistema de Registro de Asistencias

## 🎯 Descripción General

El sistema ahora registra **automáticamente** la asistencia de las personas cuando son reconocidas por el ESP32-CAM, validando que tengan un turno activo en ese momento.

---

## 🔄 Flujo de Trabajo

### 1️⃣ Modo Registro (Manual)
**Cuando presionas el botón "Registrar Rostro" en el ESP32:**
- Se captura la imagen con el nombre especificado
- Se envía al backend con topic: `test/registro/{nombre}/...`
- El backend guarda la imagen en `imagenes/` si no está duplicada
- Actualiza el archivo `personas.csv`
- ❌ **NO registra asistencia** (solo guarda el rostro)

### 2️⃣ Modo Asistencia (Automático)
**Cuando activas "Detección Auto" en el ESP32:**
- El ESP32 captura imágenes cada 3 segundos
- Se envía al backend con topic: `test/asistencia/...`
- El backend:
  1. 🔍 Reconoce el rostro usando face_recognition
  2. ✅ Verifica que la persona esté registrada
  3. 🕐 Verifica que tenga un turno activo en ese horario
  4. 📝 Registra la asistencia en `asistencias.csv`
  5. 📤 Envía respuesta al ESP32 vía MQTT

---

## 📁 Archivo `asistencias.csv`

### Estructura:
```csv
id,persona_id,persona_nombre,turno_id,turno_nombre,tipo,fecha_hora,dispositivo_ip
1,1,agustin,1,Mañana,entrada,2024-11-12 08:15:23,mqtt_device
2,1,agustin,1,Mañana,salida,2024-11-12 16:02:45,mqtt_device
```

### Campos:
- **id**: Identificador único del registro
- **persona_id**: ID de la persona (referencia a `personas.csv`)
- **persona_nombre**: Nombre completo de la persona
- **turno_id**: ID del turno (referencia a `turnos.csv`)
- **turno_nombre**: Nombre del turno (Mañana, Tarde, Noche)
- **tipo**: `entrada` o `salida` (se alterna automáticamente)
- **fecha_hora**: Timestamp del registro (YYYY-MM-DD HH:MM:SS)
- **dispositivo_ip**: IP del dispositivo que registró (o 'manual')

---

## 🔐 Lógica de Verificación de Turnos

### ¿Cómo se verifica el turno activo?

1. **Día de la semana**: Verifica que hoy sea un día del turno (L,M,X,J,V,S,D)
2. **Horario**: Comprueba que la hora actual esté dentro del rango del turno
3. **Turnos nocturnos**: Maneja correctamente turnos que cruzan medianoche (ej: 22:00 - 06:00)

### Ejemplo:
```
Turno: Mañana - 08:00 a 16:00 - L,M,X,J,V
Hora actual: 2024-11-12 (martes) 10:30

✅ VÁLIDO porque:
- Es martes (M está en L,M,X,J,V)
- 10:30 está entre 08:00 y 16:00
```

---

## 🔄 Lógica de Entrada/Salida

El sistema determina automáticamente si es entrada o salida:

### Reglas:
1. **Primera del día** → `entrada`
2. **Última fue entrada** → `salida`
3. **Última fue salida** → `entrada`

### Ejemplo de día típico:
```
08:05 → ENTRADA (primera del día)
12:00 → SALIDA (última fue entrada)
13:00 → ENTRADA (última fue salida)
16:30 → SALIDA (última fue entrada)
```

---

## 📡 Respuestas MQTT al ESP32

El backend envía diferentes tipos de respuesta según el resultado:

### Estados:
- `ASISTENCIA|{nombre}: ENTRADA registrada - Turno Mañana` - ✅ Asistencia registrada
- `SIN_TURNO|{nombre} no tiene turno asignado en este horario` - ⚠️ Sin turno activo
- `ERROR|Rostro no reconocido` - ❌ Persona no identificada

### Formato en ESP32:
```cpp
✅ agustin: ENTRADA registrada - Turno Mañana (color azul)
⚠️ agustin no tiene turno asignado en este horario (color naranja)
❌ Rostro no reconocido (color rojo)
```

---

## 🌐 API REST - Nuevos Endpoints

### 1. **GET** `/api/asistencias`
Obtiene todas las asistencias (opcional: filtrar por fecha)

**Query params:**
- `fecha` (opcional): YYYY-MM-DD

**Ejemplo:**
```bash
curl http://localhost:5000/api/asistencias?fecha=2024-11-12
```

**Respuesta:**
```json
{
  "success": true,
  "total": 4,
  "asistencias": [
    {
      "id": "1",
      "persona_id": "1",
      "persona_nombre": "agustin",
      "turno_id": "1",
      "turno_nombre": "Mañana",
      "tipo": "entrada",
      "fecha_hora": "2024-11-12 08:15:23",
      "dispositivo_ip": "mqtt_device"
    }
  ]
}
```

---

### 2. **GET** `/api/asistencias/hoy`
Obtiene todas las asistencias del día actual

**Ejemplo:**
```bash
curl http://localhost:5000/api/asistencias/hoy
```

**Respuesta:**
```json
{
  "success": true,
  "fecha": "2024-11-12",
  "total": 2,
  "asistencias": [...]
}
```

---

### 3. **GET** `/api/asistencias/persona/{persona_id}`
Obtiene las asistencias de una persona específica

**Query params:**
- `fecha` (opcional): YYYY-MM-DD

**Ejemplo:**
```bash
curl http://localhost:5000/api/asistencias/persona/1
curl http://localhost:5000/api/asistencias/persona/1?fecha=2024-11-12
```

**Respuesta:**
```json
{
  "success": true,
  "persona": {
    "id": "1",
    "nombre": "agustin",
    "fecha_registro": "2024-11-10 15:30:00",
    "total_imagenes": "5"
  },
  "total": 4,
  "asistencias": [...]
}
```

---

### 4. **POST** `/api/asistencias/registrar`
Registra una asistencia manualmente (para correcciones o testing)

**Body:**
```json
{
  "persona_id": "1",
  "dispositivo_ip": "manual"
}
```

**Respuesta exitosa:**
```json
{
  "success": true,
  "tipo": "entrada",
  "turno": "Mañana",
  "hora": "2024-11-12 08:15:23",
  "message": "ENTRADA registrada - Turno Mañana"
}
```

**Sin turno activo:**
```json
{
  "success": false,
  "message": "agustin no tiene turno asignado en este horario"
}
```

---

## 🖥️ Interfaz Web - Nueva Pestaña "Asistencias"

### Funcionalidades:

#### 📅 **Ver Asistencias de Hoy**
- Botón "Hoy" para ver registros del día actual
- Muestra: Persona, Turno, Hora, Tipo (Entrada/Salida), Dispositivo
- 🟢 ENTRADA en verde | 🔴 SALIDA en rojo

#### 📋 **Ver Todas las Asistencias**
- Botón "Todas" para ver historial completo
- Ordenadas por fecha descendente

#### 🔍 **Buscar por Fecha**
- Selector de fecha
- Botón "Buscar" para filtrar por día específico

#### 👤 **Asistencias por Persona**
- Selector desplegable con todas las personas
- Botón "Ver Asistencias"
- Muestra historial completo de la persona seleccionada

---

## 🔧 Configuración ESP32-CAM

### Código modificado:

#### 1. Función `sendImageMQTT()`:
Ahora acepta parámetro `modoAsistencia`:
```cpp
void sendImageMQTT(String personName = "", bool modoAsistencia = false)
```

- `modoAsistencia = false` → Topic: `test/registro/{nombre}/...`
- `modoAsistencia = true` → Topic: `test/asistencia/...`

#### 2. Loop de detección automática:
```cpp
if (autoDetectionEnabled) {
  // Detectar presencia cada 3 segundos
  sendImageMQTT("", true); // Modo asistencia
}
```

#### 3. Callback MQTT actualizado:
```cpp
else if (status == "ASISTENCIA") {
  lastResponse = "<span style='color: #2196F3;'>✅ " + msg + "</span>";
} else if (status == "SIN_TURNO") {
  lastResponse = "<span style='color: #FF9800;'>⚠️ " + msg + "</span>";
}
```

---

## 📊 Casos de Uso

### Caso 1: Registro de Entrada
**Escenario:**
- Persona: Juan Pérez (ID: 2)
- Turno asignado: Mañana (08:00 - 16:00, L-V)
- Fecha/Hora: 2024-11-12 (martes) 08:05

**Flujo:**
1. ESP32 detecta rostro automáticamente
2. Backend reconoce a Juan Pérez (95% confianza)
3. Backend verifica turno: ✅ Tiene turno Mañana activo
4. Backend registra: `ENTRADA` (es su primera del día)
5. ESP32 muestra: "✅ Juan Perez: ENTRADA registrada - Turno Mañana"

---

### Caso 2: Sin Turno Activo
**Escenario:**
- Persona: María López (ID: 3)
- Turno asignado: Tarde (16:00 - 00:00, L-V)
- Fecha/Hora: 2024-11-12 (martes) 10:00

**Flujo:**
1. ESP32 detecta rostro
2. Backend reconoce a María López
3. Backend verifica turno: ❌ Turno Tarde comienza a las 16:00
4. Backend NO registra asistencia
5. ESP32 muestra: "⚠️ María López no tiene turno asignado en este horario"

---

### Caso 3: Registro Manual de Rostro
**Escenario:**
- Nuevo empleado: Carlos Ruiz
- Acción: Presionar botón "Registrar Rostro"

**Flujo:**
1. Ingresar nombre: "Carlos Ruiz"
2. ESP32 captura imagen
3. Backend detecta rostro
4. Backend verifica: NO está duplicado
5. Backend guarda imagen en `imagenes/carlos_ruiz_timestamp.jpg`
6. Backend actualiza `personas.csv`
7. ❌ NO registra asistencia (es solo registro)
8. ESP32 muestra: "✅ Carlos Ruiz registrado exitosamente!"

---

## 🔍 Testing

### 1. Probar registro de asistencia manual:
```bash
curl -X POST http://localhost:5000/api/asistencias/registrar \
  -H "Content-Type: application/json" \
  -d '{"persona_id":"1","dispositivo_ip":"test"}'
```

### 2. Ver asistencias de hoy:
```bash
curl http://localhost:5000/api/asistencias/hoy
```

### 3. Ver asistencias de una persona:
```bash
curl http://localhost:5000/api/asistencias/persona/1
```

### 4. Filtrar por fecha:
```bash
curl "http://localhost:5000/api/asistencias?fecha=2024-11-12"
```

---

## 📝 Notas Importantes

1. **Frecuencia de detección**: 3 segundos (configurable en ESP32)
2. **Umbral de reconocimiento**: 40% de confianza mínima
3. **Tolerancia de rostros**: 0.6 (face_recognition)
4. **Alternancia automática**: El sistema alterna entre entrada/salida
5. **Solo con turno activo**: No registra si no hay turno en ese horario
6. **Turnos nocturnos**: Soporta turnos que cruzan medianoche

---

## 🚀 Próximos Pasos

1. ✅ Sistema básico de asistencias implementado
2. 📊 Dashboard de estadísticas (horas trabajadas, tardanzas)
3. 📧 Notificaciones por correo/SMS
4. 📱 App móvil para consulta
5. 🗄️ Migración de CSV a base de datos SQL
6. 📈 Reportes mensuales en PDF
7. 🔔 Alertas de ausencias

---

## 🆘 Troubleshooting

### Problema: "No tiene turno asignado"
**Solución:** Verificar:
- Que la persona tenga un turno asignado en `asignaciones.csv`
- Que el día actual esté en los días del turno (L,M,X,J,V,S,D)
- Que la hora actual esté dentro del rango del turno

### Problema: "Rostro no reconocido"
**Solución:**
- Verificar que existan imágenes en `imagenes/`
- Asegurarse de que el reconocimiento tenga > 40% confianza
- Re-registrar el rostro con mejor iluminación

### Problema: No registra asistencia
**Solución:**
- Verificar que `autoDetectionEnabled = true` en ESP32
- Revisar logs del backend (Docker logs)
- Confirmar que el topic MQTT sea `test/asistencia/...`

---

## 📞 Contacto y Soporte

Para más información sobre el sistema, consulta:
- `README.md` - Configuración general
- `INTEGRACION_ESP32.md` - Comunicación bidireccional
- `CAMBIOS_REGISTRO.md` - Sistema de registro de rostros

---

**🎉 ¡Sistema de asistencias completamente funcional!**
