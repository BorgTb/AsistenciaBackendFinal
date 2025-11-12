# 🚀 Guía Rápida - Sistema de Gestión de Turnos

## ⚡ Inicio Rápido (5 minutos)

### 1️⃣ Iniciar el Sistema
```bash
docker-compose up -d --build
```

### 2️⃣ Verificar que Funciona
```bash
curl http://localhost:5000/api/health
```

**Respuesta esperada:**
```json
{
  "success": true,
  "status": "running",
  "mqtt_connected": true,
  "total_personas": 0,
  "total_turnos": 3
}
```

### 3️⃣ Abrir Interfaz Web
1. Abrir `test_api.html` en el navegador
2. ¡Listo para usar!

---

## 📋 Casos de Uso Comunes

### 🆕 Registrar Nueva Persona
**Método 1: ESP32-CAM**
1. Acceder a la IP del ESP32
2. Ingresar nombre: "Juan Perez"
3. Clic en "Registrar Nuevo Rostro"
4. Automáticamente aparece en el sistema

**Método 2: API (si ya tienes imagen)**
```bash
# Se registra automáticamente al enviar via MQTT
```

### 📊 Ver Todas las Personas
```bash
curl http://localhost:5000/api/personas
```

**Respuesta:**
```json
{
  "success": true,
  "total": 2,
  "personas": [
    {
      "id": "1",
      "nombre": "Juan Perez",
      "fecha_registro": "2024-01-15 10:30:00",
      "total_imagenes": "3"
    },
    {
      "id": "2",
      "nombre": "Maria Garcia",
      "fecha_registro": "2024-01-16 14:20:00",
      "total_imagenes": "1"
    }
  ]
}
```

### 🕐 Crear Nuevo Turno
```bash
curl -X POST http://localhost:5000/api/turnos \
  -H "Content-Type: application/json" \
  -d '{
    "nombre_turno": "Fin de Semana",
    "hora_inicio": "09:00",
    "hora_fin": "18:00",
    "dias_semana": "S,D"
  }'
```

### ➕ Asignar Turno a Persona
```bash
curl -X POST http://localhost:5000/api/asignaciones \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "1",
    "turno_id": "2"
  }'
```

### 👤 Ver Detalle de Persona con sus Turnos
```bash
curl http://localhost:5000/api/personas/1
```

**Respuesta:**
```json
{
  "success": true,
  "persona": {
    "id": "1",
    "nombre": "Juan Perez",
    "fecha_registro": "2024-01-15 10:30:00",
    "total_imagenes": "3",
    "turnos": [
      {
        "id": "1",
        "nombre_turno": "Mañana",
        "hora_inicio": "08:00",
        "hora_fin": "16:00",
        "dias_semana": "L,M,X,J,V",
        "fecha_asignacion": "2024-01-15 11:00:00"
      },
      {
        "id": "2",
        "nombre_turno": "Tarde",
        "hora_inicio": "16:00",
        "hora_fin": "00:00",
        "dias_semana": "L,M,X,J,V",
        "fecha_asignacion": "2024-01-15 11:05:00"
      }
    ]
  }
}
```

### 🗑️ Eliminar Asignación
```bash
curl -X DELETE http://localhost:5000/api/asignaciones/1/2
```

---

## 🌐 Desde JavaScript (Frontend)

### Obtener Personas
```javascript
async function getPersonas() {
  const response = await fetch('http://localhost:5000/api/personas');
  const data = await response.json();
  console.log(data.personas);
}
```

### Crear Turno
```javascript
async function crearTurno() {
  const response = await fetch('http://localhost:5000/api/turnos', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      nombre_turno: 'Noche',
      hora_inicio: '22:00',
      hora_fin: '06:00',
      dias_semana: 'L,M,X,J,V,S,D'
    })
  });
  const data = await response.json();
  console.log(data);
}
```

### Asignar Turno
```javascript
async function asignarTurno(personaId, turnoId) {
  const response = await fetch('http://localhost:5000/api/asignaciones', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      persona_id: personaId,
      turno_id: turnoId
    })
  });
  const data = await response.json();
  alert(data.message);
}
```

---

## 🐍 Desde Python

### Script Completo
```python
import requests

BASE_URL = 'http://localhost:5000/api'

# 1. Obtener todas las personas
personas = requests.get(f'{BASE_URL}/personas').json()
print(f"Total personas: {personas['total']}")

# 2. Obtener todos los turnos
turnos = requests.get(f'{BASE_URL}/turnos').json()
print(f"Total turnos: {turnos['total']}")

# 3. Crear nuevo turno
nuevo_turno = {
    'nombre_turno': 'Medio Día',
    'hora_inicio': '10:00',
    'hora_fin': '18:00',
    'dias_semana': 'L,M,X,J,V'
}
response = requests.post(f'{BASE_URL}/turnos', json=nuevo_turno)
print(response.json())

# 4. Asignar turno a primera persona
if personas['total'] > 0 and turnos['total'] > 0:
    asignacion = {
        'persona_id': personas['personas'][0]['id'],
        'turno_id': turnos['turnos'][0]['id']
    }
    response = requests.post(f'{BASE_URL}/asignaciones', json=asignacion)
    print(response.json())

# 5. Ver detalle de persona
persona_id = personas['personas'][0]['id']
detalle = requests.get(f'{BASE_URL}/personas/{persona_id}').json()
print(f"\nDetalle de {detalle['persona']['nombre']}:")
print(f"Turnos asignados: {len(detalle['persona']['turnos'])}")
for turno in detalle['persona']['turnos']:
    print(f"  - {turno['nombre_turno']}: {turno['hora_inicio']}-{turno['hora_fin']}")
```

---

## 📁 Acceso Directo a Datos

### Ver CSVs
```bash
# Personas registradas
cat data/personas.csv

# Turnos disponibles
cat data/turnos.csv

# Asignaciones
cat data/asignaciones.csv
```

### Editar CSVs Manualmente (opcional)
```bash
# Abrir con editor
notepad data/personas.csv
notepad data/turnos.csv
notepad data/asignaciones.csv
```

⚠️ **Nota:** Los cambios manuales se reflejan en la API inmediatamente.

---

## 🔍 Debugging

### Ver Logs en Tiempo Real
```bash
docker-compose logs -f reconocimiento
```

### Verificar Contenedor
```bash
docker-compose ps
```

### Reiniciar Sistema
```bash
docker-compose restart reconocimiento
```

### Limpiar y Reiniciar Todo
```bash
docker-compose down
docker-compose up -d --build
```

### Ver Estado de MQTT
```bash
docker-compose logs mosquitto
```

---

## 💡 Tips y Trucos

### 1. Backup de Datos
```bash
# Respaldar CSVs
cp -r data data_backup_$(date +%Y%m%d)

# Respaldar imágenes
cp -r imagenes imagenes_backup_$(date +%Y%m%d)
```

### 2. Limpiar Datos de Prueba
```bash
# Eliminar CSVs (se recrearán con defaults)
rm data/*.csv

# Reiniciar contenedor
docker-compose restart reconocimiento
```

### 3. Monitorear API
```bash
# Hacer peticiones continuas para monitoreo
watch -n 5 'curl -s http://localhost:5000/api/health | jq'
```

### 4. Exportar Datos
```bash
# Convertir CSV a JSON
python -c "
import csv, json
with open('data/personas.csv') as f:
    data = list(csv.DictReader(f))
print(json.dumps(data, indent=2))
"
```

---

## ⚡ Atajos de Teclado (test_api.html)

- **Tab**: Navegar entre secciones
- **Enter**: Confirmar asignación (en formulario)
- **F5**: Actualizar página y datos

---

## 📊 Datos de Ejemplo para Pruebas

### Turnos Predeterminados (ya incluidos)
1. **Mañana**: 08:00 - 16:00 (L-V)
2. **Tarde**: 16:00 - 00:00 (L-V)
3. **Noche**: 00:00 - 08:00 (L-V)

### Crear Más Turnos
```bash
# Fin de Semana
curl -X POST http://localhost:5000/api/turnos \
  -H "Content-Type: application/json" \
  -d '{"nombre_turno":"Fin de Semana","hora_inicio":"09:00","hora_fin":"18:00","dias_semana":"S,D"}'

# Medio Día
curl -X POST http://localhost:5000/api/turnos \
  -H "Content-Type: application/json" \
  -d '{"nombre_turno":"Medio Día","hora_inicio":"10:00","hora_fin":"18:00","dias_semana":"L,M,X,J,V"}'

# 24 Horas
curl -X POST http://localhost:5000/api/turnos \
  -H "Content-Type: application/json" \
  -d '{"nombre_turno":"24 Horas","hora_inicio":"00:00","hora_fin":"23:59","dias_semana":"L,M,X,J,V,S,D"}'
```

---

## 🎯 Checklist de Inicio

- [ ] Contenedores corriendo: `docker-compose ps`
- [ ] API responde: `curl http://localhost:5000/api/health`
- [ ] Interfaz web abierta: `test_api.html`
- [ ] ESP32-CAM conectado y funcional
- [ ] CSVs creados en carpeta `data/`
- [ ] Puerto 5000 accesible
- [ ] Puerto 1883 MQTT funcionando

---

## 🆘 Problemas Comunes

### API no responde
```bash
# Verificar logs
docker-compose logs reconocimiento

# Reiniciar
docker-compose restart reconocimiento
```

### MQTT no conecta
```bash
# Verificar mosquitto
docker-compose logs mosquitto

# Reiniciar broker
docker-compose restart mosquitto
```

### CSVs no se crean
```bash
# Verificar permisos de carpeta data/
ls -la data/

# Reiniciar con logs
docker-compose restart reconocimiento
docker-compose logs -f reconocimiento
```

### Puerto 5000 ocupado
```bash
# Ver qué usa el puerto
netstat -ano | findstr :5000

# Cambiar puerto en docker-compose.yml
# "5001:5000" en lugar de "5000:5000"
```

---

**¡Sistema listo para usar!** 🎉

Para más información, consulta:
- `API_DOCUMENTATION.md` - Documentación completa
- `IMPLEMENTACION.md` - Detalles técnicos
- `test_api.html` - Interfaz web funcional
