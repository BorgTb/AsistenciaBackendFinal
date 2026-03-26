#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <Adafruit_Fingerprint.h>

// Sensor de huellas (RX=GPIO13, TX=GPIO12)
HardwareSerial FingerSerial(2);  
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&FingerSerial);

WebServer server(80);

// ===== AP para configuración =====
const char* apSSID = "ESP32-ASISTENCIA";
const char* apPASS = "12345678";

// ===== Variables WiFi configurables =====
String savedSSID = "";
String savedPASS = "";
bool wifiConfigMode = true;

// ===== Variables para escaneo automático =====
unsigned long lastFingerCheck = 0;
const unsigned long FINGER_CHECK_INTERVAL = 500;
int lastFingerID = -1;
unsigned long lastFingerTime = 0;
const unsigned long FINGER_DEBOUNCE = 3000;

// ======================= INICIALIZAR SPIFFS ==========================
void initSPIFFS() {
  if (!SPIFFS.begin(true)) {
    Serial.println("Error montando SPIFFS");
    return;
  }

  const char* files[] = {
    "/personas.json",
    "/turnos.json",
    "/asignaciones.json",
    "/asistencias.json",
    "/wifi.json"
  };

  for (auto f : files) {
    if (!SPIFFS.exists(f)) {
      File file = SPIFFS.open(f, "w");
      if (String(f) == "/wifi.json") {
        file.println("{\"ssid\":\"\",\"pass\":\"\"}");
      } else {
        file.println("[]");
      }
      file.close();
      Serial.printf("Creado %s\n", f);
    }
  }
  
  Serial.println("SPIFFS inicializado");
}

// ======================= CARGAR/GUARDAR WIFI =========================
void loadWiFiConfig() {
  File file = SPIFFS.open("/wifi.json", "r");
  if (file) {
    DynamicJsonDocument doc(512);
    deserializeJson(doc, file);
    savedSSID = doc["ssid"].as<String>();
    savedPASS = doc["pass"].as<String>();
    file.close();
  }
}

void saveWiFiConfig(String ssid, String pass) {
  DynamicJsonDocument doc(512);
  doc["ssid"] = ssid;
  doc["pass"] = pass;
  File file = SPIFFS.open("/wifi.json", "w");
  serializeJson(doc, file);
  file.close();
}

// ======================= FUNCIONES JSON =============================
JsonArray loadArray(const char* path, DynamicJsonDocument &doc) {
  File file = SPIFFS.open(path, "r");
  String content = file.readString();
  file.close();
  deserializeJson(doc, content);
  return doc.as<JsonArray>();
}

void saveArray(const char* path, DynamicJsonDocument &doc) {
  File file = SPIFFS.open(path, "w");
  serializeJson(doc, file);
  file.close();
}

// ======================= BUSCAR SLOT LIBRE DE HUELLA =================
int encontrarSlotLibre() {
  for (int id = 1; id < 127; id++) {
    if (finger.loadModel(id) != FINGERPRINT_OK)
      return id;
  }
  return -1;
}

// ======================= ENROLL HUELLA ===============================
bool registrarHuella(int slot) {
  Serial.printf("Iniciando enrolamiento en slot %d...\n", slot);

  int p = -1;
  int intentos = 0;

  Serial.println("Coloque el dedo...");
  while (p != FINGERPRINT_OK && intentos < 50) {
    p = finger.getImage();
    delay(100);
    intentos++;
  }
  
  if (p != FINGERPRINT_OK) {
    Serial.println("Timeout esperando dedo");
    return false;
  }

  p = finger.image2Tz(1);
  if (p != FINGERPRINT_OK) {
    Serial.println("Error procesando imagen 1");
    return false;
  }

  Serial.println("Retire el dedo");
  delay(2000);

  p = -1;
  intentos = 0;
  Serial.println("Coloque nuevamente el mismo dedo...");
  while (p != FINGERPRINT_OK && intentos < 50) {
    p = finger.getImage();
    delay(100);
    intentos++;
  }
  
  if (p != FINGERPRINT_OK) {
    Serial.println("Timeout en segunda captura");
    return false;
  }

  p = finger.image2Tz(2);
  if (p != FINGERPRINT_OK) {
    Serial.println("Error procesando imagen 2");
    return false;
  }

  p = finger.createModel();
  if (p != FINGERPRINT_OK) {
    Serial.println("Error creando modelo");
    return false;
  }

  p = finger.storeModel(slot);
  if (p == FINGERPRINT_OK) {
    Serial.println("Huella guardada correctamente");
    return true;
  }

  Serial.println("Error guardando huella");
  return false;
}

// ======================= CONFIGURAR WIFI =============================
void handleWiFiConfig() {
  if (server.hasArg("ssid") && server.hasArg("pass")) {
    String ssid = server.arg("ssid");
    String pass = server.arg("pass");
    
    saveWiFiConfig(ssid, pass);
    server.send(200, "text/plain", "Configuracion guardada. Reiniciando...");
    delay(1000);
    ESP.restart();
  } else {
    server.send(400, "text/plain", "Faltan parametros");
  }
}

// ======================= REGISTRAR PERSONA ===========================
void handleRegisterUser() {
  if (!server.hasArg("name") || !server.hasArg("rut") || !server.hasArg("email")) {
    server.send(400, "text/plain", "Faltan datos requeridos");
    return;
  }

  String nombre = server.arg("name");
  String rut = server.arg("rut");
  String email = server.arg("email");

  DynamicJsonDocument doc(4096);
  JsonArray personas = loadArray("/personas.json", doc);

  // Verificar si ya existe por RUT
  for (JsonObject p : personas) {
    if (p["rut"] == rut) {
      server.send(400, "text/plain", "RUT ya registrado");
      return;
    }
  }

  int idInterno = personas.size() + 1;
  int huellaSlot = encontrarSlotLibre();

  if (huellaSlot < 0) {
    server.send(500, "text/plain", "No hay slots libres en el sensor");
    return;
  }

  Serial.printf("Registrando huella para: %s\n", nombre.c_str());
  if (!registrarHuella(huellaSlot)) {
    server.send(500, "text/plain", "Error registrando huella. Intente nuevamente.");
    return;
  }

  JsonObject p = personas.createNestedObject();
  p["id"] = String(idInterno);
  p["nombre"] = nombre;
  p["rut"] = rut;
  p["email"] = email;
  p["huella_id"] = huellaSlot;
  p["fecha_registro"] = millis() / 1000;

  saveArray("/personas.json", doc);

  server.send(200, "text/plain",
    "Usuario registrado\nNombre: " + nombre +
    "\nRUT: " + rut +
    "\nEmail: " + email +
    "\nHuella ID: " + String(huellaSlot));
}

// ======================= CREAR TURNO ===============================
void handleCreateTurn() {
  if (!server.hasArg("nombre") ||
      !server.hasArg("inicio") ||
      !server.hasArg("fin") ||
      !server.hasArg("dias")) {
    server.send(400, "text/plain", "Datos incompletos");
    return;
  }

  DynamicJsonDocument doc(4096);
  JsonArray turnos = loadArray("/turnos.json", doc);

  JsonObject t = turnos.createNestedObject();
  t["id"] = String(turnos.size() + 1);
  t["nombre"] = server.arg("nombre");
  t["inicio"] = server.arg("inicio");
  t["fin"] = server.arg("fin");
  t["dias"] = server.arg("dias");

  saveArray("/turnos.json", doc);
  server.send(200, "text/plain", "Turno creado");
}

// ======================= ASIGNAR TURNO =============================
void handleAssignTurn() {
  if (!server.hasArg("persona") || !server.hasArg("turno")) {
    server.send(400, "text/plain", "Falta persona o turno");
    return;
  }

  DynamicJsonDocument doc(4096);
  JsonArray asignaciones = loadArray("/asignaciones.json", doc);

  String personaId = server.arg("persona");
  String turnoId = server.arg("turno");
  
  for (JsonObject a : asignaciones) {
    if (a["persona_id"] == personaId) {
      server.send(400, "text/plain", "Persona ya tiene turno asignado");
      return;
    }
  }

  JsonObject a = asignaciones.createNestedObject();
  a["persona_id"] = personaId;
  a["turno_id"] = turnoId;
  a["fecha_asignacion"] = millis() / 1000;

  saveArray("/asignaciones.json", doc);
  server.send(200, "text/plain", "Turno asignado");
}

// ======================= VERIFICAR TURNO ACTIVO =====================
bool turnoActivo(String personaId) {
  DynamicJsonDocument docA(4096);
  DynamicJsonDocument docT(4096);

  JsonArray asign = loadArray("/asignaciones.json", docA);
  JsonArray turnos = loadArray("/turnos.json", docT);

  for (JsonObject a : asign) {
    if (a["persona_id"] == personaId) {
      String turnoId = a["turno_id"];
      for (JsonObject t : turnos) {
        if (t["id"] == turnoId) {
          return true;
        }
      }
    }
  }
  return false;
}

// ======================= REGISTRAR ASISTENCIA =======================
String registrarAsistenciaAutomatica(int huellaID) {
  DynamicJsonDocument docP(4096);
  JsonArray personas = loadArray("/personas.json", docP);

  String personaId = "";
  String nombre = "";

  for (JsonObject p : personas) {
    if (p["huella_id"] == huellaID) {
      personaId = p["id"].as<String>();
      nombre = p["nombre"].as<String>();
      break;
    }
  }

  if (personaId == "") {
    return "Huella no asociada a usuario";
  }

  if (!turnoActivo(personaId)) {
    return "Usuario sin turno asignado: " + nombre;
  }

  DynamicJsonDocument docA(4096);
  JsonArray asist = loadArray("/asistencias.json", docA);

  String tipo = "entrada";
  for (int i = asist.size() - 1; i >= 0; i--) {
    JsonObject a = asist[i];
    if (a["persona_id"] == personaId) {
      tipo = (a["tipo"] == "entrada") ? "salida" : "entrada";
      break;
    }
  }

  JsonObject a = asist.createNestedObject();
  a["persona_id"] = personaId;
  a["nombre"] = nombre;
  a["tipo"] = tipo;
  a["timestamp"] = millis() / 1000;

  saveArray("/asistencias.json", docA);

  String tipoMayus = tipo;
  tipoMayus.toUpperCase();
  return tipoMayus + " registrada\nUsuario: " + nombre;
}

void handleMarcarAsistencia() {
  Serial.println("Esperando huella...");

  int p = finger.getImage();
  if (p != FINGERPRINT_OK) {
    server.send(500, "text/plain", "No se detecta huella");
    return;
  }

  finger.image2Tz();
  finger.fingerSearch();

  if (finger.fingerID < 1) {
    server.send(500, "text/plain", "Huella no encontrada");
    return;
  }

  int huellaID = finger.fingerID;
  Serial.printf("Huella reconocida: ID %d\n", huellaID);

  String resultado = registrarAsistenciaAutomatica(huellaID);
  server.send(200, "text/plain", resultado);
}

// ======================= APIs REST ===============================
void handleGetPersonas() {
  File file = SPIFFS.open("/personas.json", "r");
  String content = file.readString();
  file.close();
  server.send(200, "application/json", content);
}

void handleGetTurnos() {
  File file = SPIFFS.open("/turnos.json", "r");
  String content = file.readString();
  file.close();
  server.send(200, "application/json", content);
}

void handleGetAsignaciones() {
  File file = SPIFFS.open("/asignaciones.json", "r");
  String content = file.readString();
  file.close();
  server.send(200, "application/json", content);
}

void handleGetAsistencias() {
  File file = SPIFFS.open("/asistencias.json", "r");
  String content = file.readString();
  file.close();
  server.send(200, "application/json", content);
}

// ======================= LIMPIAR DATOS ===============================
void handleLimpiarDatos() {
  if (!server.hasArg("codigo")) {
    server.send(400, "text/plain", "Falta codigo de seguridad");
    return;
  }

  String codigo = server.arg("codigo");
  
  if (codigo != "1234") {
    server.send(403, "text/plain", "Codigo incorrecto");
    return;
  }

  Serial.println("\nLIMPIANDO TODOS LOS DATOS...");

  const char* files[] = {
    "/personas.json",
    "/turnos.json",
    "/asignaciones.json",
    "/asistencias.json"
  };

  for (auto f : files) {
    File file = SPIFFS.open(f, "w");
    file.println("[]");
    file.close();
    Serial.printf("Limpiado %s\n", f);
  }

  Serial.println("Limpiando huellas del sensor...");
  for (int id = 1; id < 127; id++) {
    finger.deleteModel(id);
  }

  Serial.println("Todos los datos han sido eliminados\n");
  server.send(200, "text/plain", "Sistema limpiado correctamente\n\nSe eliminaron:\n- Todas las personas\n- Todos los turnos\n- Todas las asignaciones\n- Todas las asistencias\n- Todas las huellas del sensor");
}

// ======================= PAGINA DE CONFIGURACION WIFI ================
const char* wifiConfigPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Configuracion WiFi</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:30px;max-width:400px;width:100%}
h1{color:#667eea;text-align:center;margin-bottom:20px;font-size:24px}
.form-group{margin-bottom:15px}
label{display:block;color:#333;font-weight:600;margin-bottom:5px}
input{width:100%;padding:12px;border:2px solid #ddd;border-radius:8px;font-size:14px}
input:focus{outline:none;border-color:#667eea}
button{width:100%;padding:14px;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;margin-top:10px;color:white;background:#667eea}
button:hover{background:#5568c0}
.btn-secondary{background:#6c757d;margin-top:5px}
.btn-secondary:hover{background:#5a6268}
.status{margin-top:15px;padding:12px;border-radius:8px;text-align:center;display:none}
.status.show{display:block}
.status.success{background:#d4edda;color:#155724}
.status.error{background:#f8d7da;color:#721c24}
</style>
</head>
<body>
<div class="container">
<h1>Configuracion WiFi</h1>
<form id="wifiForm">
<div class="form-group">
<label for="ssid">SSID</label>
<input type="text" id="ssid" placeholder="Nombre de la red WiFi" required>
</div>
<div class="form-group">
<label for="password">Password</label>
<input type="password" id="password" placeholder="Contraseña">
</div>
<button type="submit">Guardar y Reiniciar</button>
<button type="button" class="btn-secondary" onclick="window.location.href='/'">Volver</button>
</form>
<div id="status" class="status"></div>
</div>
<script>
document.getElementById('wifiForm').addEventListener('submit', async (e) => {
e.preventDefault();
const ssid = document.getElementById('ssid').value;
const pass = document.getElementById('password').value;
const status = document.getElementById('status');
try {
const r = await fetch('/wifi-config?ssid=' + encodeURIComponent(ssid) + '&pass=' + encodeURIComponent(pass));
const msg = await r.text();
status.className = 'status show success';
status.textContent = msg;
setTimeout(() => location.href = '/', 3000);
} catch (e) {
status.className = 'status show error';
status.textContent = 'Error: ' + e.message;
}
});
</script>
</body>
</html>
)rawliteral";

// ======================= HTML PRINCIPAL ===============================
const char* htmlPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ESP32 Sistema Asistencia</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:20px;max-width:600px;margin:0 auto}
h1{color:#333;text-align:center;margin-bottom:10px}
.status-bar{background:#f5f5f5;padding:10px;border-radius:8px;margin-bottom:15px;text-align:center}
.status-item{display:flex;justify-content:space-between;padding:6px 0}
button{width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-bottom:8px;color:white;transition:0.3s}
button:hover{transform:scale(1.02)}
button:active{transform:scale(0.98)}
.btn-primary{background:#667eea}
.btn-success{background:#4CAF50}
.btn-warning{background:#ff9800}
.btn-danger{background:#f44336}
.btn-info{background:#00bcd4}
.status{background:#f5f5f5;padding:12px;border-radius:8px;margin-top:10px;text-align:center;min-height:50px;display:flex;align-items:center;justify-content:center;font-size:13px}
.section{margin:15px 0;padding:10px;background:#f9f9f9;border-radius:8px}
h3{color:#667eea;margin-bottom:8px;font-size:16px}
</style>
</head>
<body>
<div class="container">
<h1>ESP32 Sistema Asistencia</h1>
<div class="status-bar">
<div class="status-item"><span>Modo:</span><strong>OFFLINE</strong></div>
<div class="status-item"><span>Sensor:</span><strong style="color:#4CAF50">Activo</strong></div>
</div>

<div class="section">
<h3>Registro</h3>
<button class="btn-warning" onclick="window.location.href='/register'">Registrar Persona</button>
</div>

<div class="section">
<h3>Asistencia Automatica</h3>
<div style="background:#e8f5e9;padding:15px;border-radius:8px;margin-bottom:10px;text-align:center">
<strong style="color:#4CAF50">Modo Automatico Activado</strong><br>
<small style="color:#666">Coloque su dedo en el sensor para marcar entrada/salida</small>
</div>
<button class="btn-success" onclick="marcar()">Marcar Manual</button>
</div>

<div class="section">
<h3>Gestion</h3>
<button class="btn-primary" onclick="window.location.href='/gestion'">Gestion Turnos</button>
<button class="btn-info" onclick="window.location.href='/asistencias'">Ver Asistencias</button>
<button class="btn-info" onclick="window.location.href='/personas'">Ver Personas</button>
<button class="btn-primary" onclick="window.location.href='/wifi-setup'">Configurar WiFi</button>
</div>

<div class="section">
<h3>Zona de Peligro</h3>
<button class="btn-danger" onclick="limpiarDatos()">Limpiar Todos los Datos</button>
</div>

<div class="status" id="status">Sistema listo</div>
</div>
<script>
async function marcar(){
document.getElementById('status').innerHTML='Esperando huella...';
try{
const r=await fetch('/marcar');
const msg=await r.text();
document.getElementById('status').innerHTML=msg.replace(/\n/g,'<br>');
}catch(e){
document.getElementById('status').innerHTML='Error: '+e.message;
}
}
async function limpiarDatos(){
const codigo=prompt('ADVERTENCIA: Esto eliminara TODOS los datos del sistema.\\n\\nIngrese el codigo de seguridad para continuar:');
if(!codigo){return;}
if(!confirm('Esta SEGURO de que desea eliminar:\\n\\n- Todas las personas\\n- Todos los turnos\\n- Todas las asignaciones\\n- Todas las asistencias\\n- Todas las huellas del sensor\\n\\nEsta accion NO se puede deshacer.')){return;}
document.getElementById('status').innerHTML='Limpiando datos...';
try{
const r=await fetch('/limpiar?codigo='+encodeURIComponent(codigo));
const msg=await r.text();
document.getElementById('status').innerHTML=msg.replace(/\n/g,'<br>');
if(msg.includes('correctamente')){
setTimeout(()=>{location.reload();},3000);
}
}catch(e){
document.getElementById('status').innerHTML='Error: '+e.message;
}
}
setInterval(()=>{
document.getElementById('status').innerHTML='Sistema listo';
},5000);
</script>
</body>
</html>
)rawliteral";

// ===== RESTO DE PAGINAS HTML (sin emojis) =====
const char* registerPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Registrar Persona</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:20px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:30px;max-width:900px;margin:0 auto}
h1{color:#333;text-align:center;margin-bottom:20px;font-size:24px}
.content{display:flex;gap:20px;flex-wrap:wrap}
.form-section{flex:1;min-width:300px}
.camera-section{flex:1;min-width:300px;background:#f5f5f5;border-radius:10px;padding:20px;text-align:center}
.form-group{margin-bottom:15px}
label{display:block;color:#333;font-weight:600;margin-bottom:5px;font-size:14px}
input{width:100%;padding:12px;border:2px solid #ddd;border-radius:8px;font-size:14px}
input:focus{outline:none;border-color:#667eea}
button{width:100%;padding:14px;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;margin-top:10px;color:white;transition:0.3s}
button:hover{transform:scale(1.02)}
.btn-success{background:#4CAF50}
.btn-success:hover{background:#45a049}
.btn-secondary{background:#6c757d;margin-top:5px}
.btn-secondary:hover{background:#5a6268}
.btn-info{background:#00bcd4}
.btn-info:hover{background:#0097a7}
.status{margin-top:15px;padding:12px;border-radius:8px;text-align:center}
.status.success{background:#d4edda;color:#155724}
.status.error{background:#f8d7da;color:#721c24}
.status.info{background:#d1ecf1;color:#0c5460}
.camera-placeholder{background:#e0e0e0;border:2px dashed #999;border-radius:8px;padding:40px;margin:20px 0;min-height:300px;display:flex;align-items:center;justify-content:center;color:#666;font-size:14px}
#videoPreview{width:100%;border-radius:8px;display:none}
</style>
</head>
<body>
<div class="container">
<h1>Registrar Persona</h1>
<div class="content">
<div class="form-section">
<div class="form-group">
<label for="personName">Nombre Completo *</label>
<input type="text" id="personName" placeholder="Ej: Juan Perez" required>
</div>
<div class="form-group">
<label for="personRut">RUT *</label>
<input type="text" id="personRut" placeholder="Ej: 12345678-9" required>
</div>
<div class="form-group">
<label for="personEmail">Email *</label>
<input type="email" id="personEmail" placeholder="Ej: juan@email.com" required>
</div>
<button class="btn-success" onclick="registrar()">Registrar con Huella</button>
<button class="btn-info" onclick="window.location.href='/personas'">Ver Personas</button>
<button class="btn-secondary" onclick="window.location.href='/'">Volver</button>
<div id="status" class="status info">
Complete los datos y presione Registrar<br>
<small>Siga las instrucciones del monitor serial para la huella</small>
</div>
</div>
<div class="camera-section">
<h3 style="color:#667eea;margin-bottom:10px">Vista Previa Camara</h3>
<div class="camera-placeholder">
<video id="videoPreview" autoplay></video>
<div id="cameraPlaceholder">Camara no disponible en modo offline<br><small>Funcionalidad reservada para futuras versiones</small></div>
</div>
<small style="color:#666">Template para integracion futura</small>
</div>
</div>
</div>
<script>
async function registrar(){
const nombre=document.getElementById('personName').value.trim();
const rut=document.getElementById('personRut').value.trim();
const email=document.getElementById('personEmail').value.trim();
if(!nombre||!rut||!email){
alert('Por favor complete todos los campos');
return;
}
const status=document.getElementById('status');
status.className='status info';
status.innerHTML='Iniciando registro de huella...<br><small>Coloque el dedo en el sensor cuando se indique</small>';
try{
const r=await fetch('/registrar?name='+encodeURIComponent(nombre)+'&rut='+encodeURIComponent(rut)+'&email='+encodeURIComponent(email));
const msg=await r.text();
if(r.ok){
status.className='status success';
status.innerHTML=msg.replace(/\n/g,'<br>');
document.getElementById('personName').value='';
document.getElementById('personRut').value='';
document.getElementById('personEmail').value='';
setTimeout(()=>{
status.className='status info';
status.innerHTML='Listo para registrar otra persona';
},3000);
}else{
status.className='status error';
status.innerHTML=msg;
}
}catch(e){
status.className='status error';
status.innerHTML='Error: '+e.message;
}
}
</script>
</body>
</html>
)rawliteral";

const char* gestionPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Gestion de Turnos</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:20px;max-width:900px;margin:0 auto}
h1{color:#333;text-align:center;margin-bottom:15px;font-size:22px}
h2{color:#667eea;font-size:18px;margin:15px 0 10px 0;border-bottom:2px solid #667eea;padding-bottom:5px}
.section{background:#f9f9f9;padding:15px;border-radius:8px;margin-bottom:15px}
.list{max-height:300px;overflow-y:auto;background:white;border:1px solid #ddd;border-radius:6px;padding:10px;margin:10px 0}
.item{padding:8px;margin:5px 0;background:#f5f5f5;border-left:4px solid #667eea;border-radius:4px;font-size:13px}
button{width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-bottom:8px;color:white;background:#667eea}
button:hover{background:#5568c0}
.badge{display:inline-block;padding:3px 8px;border-radius:10px;font-size:11px;background:#e0e0e0;margin-left:5px}
</style>
</head>
<body>
<div class="container">
<h1>Gestion de Turnos</h1>

<div class="section">
<h2>Turnos <span class="badge" id="countTurnos">0</span></h2>
<div class="list" id="listTurnos">Cargando...</div>
<button onclick="window.location.href='/turnos'">Gestionar Turnos</button>
</div>

<div class="section">
<h2>Asignaciones <span class="badge" id="countAsignaciones">0</span></h2>
<div class="list" id="listAsignaciones">Cargando...</div>
<button onclick="window.location.href='/asignaciones-view'">Gestionar Asignaciones</button>
</div>

<button onclick="window.location.href='/'">Volver al Inicio</button>
</div>

<script>
let personas=[];
let turnos=[];
let asignaciones=[];

async function cargarPersonas(){
try{
const r=await fetch('/api/personas');
personas=await r.json();
}catch(e){}
}

async function cargarTurnos(){
try{
const r=await fetch('/api/turnos');
turnos=await r.json();
document.getElementById('countTurnos').textContent=turnos.length;
const container=document.getElementById('listTurnos');
if(turnos.length===0){container.innerHTML='<div style="text-align:center;color:#999">No hay turnos</div>';return;}
let html='';
turnos.forEach(t=>{
html+=`<div class="item"><strong>${t.nombre}</strong><br><small>${t.inicio} - ${t.fin} (${t.dias})</small></div>`;
});
container.innerHTML=html;
}catch(e){document.getElementById('listTurnos').innerHTML='Error';}
}

async function cargarAsignaciones(){
try{
const r=await fetch('/api/asignaciones');
asignaciones=await r.json();
document.getElementById('countAsignaciones').textContent=asignaciones.length;
const container=document.getElementById('listAsignaciones');
if(asignaciones.length===0){container.innerHTML='<div style="text-align:center;color:#999">No hay asignaciones</div>';return;}
let html='';
asignaciones.forEach(a=>{
const persona=personas.find(p=>p.id===a.persona_id);
const turno=turnos.find(t=>t.id===a.turno_id);
const nombrePersona=persona?persona.nombre:'ID '+a.persona_id;
const nombreTurno=turno?turno.nombre:'ID '+a.turno_id;
html+=`<div class="item"><strong>${nombrePersona}</strong> -> ${nombreTurno}</div>`;
});
container.innerHTML=html;
}catch(e){document.getElementById('listAsignaciones').innerHTML='Error';}
}

cargarPersonas();
cargarTurnos();
cargarAsignaciones();
setInterval(()=>{cargarPersonas();cargarTurnos();cargarAsignaciones();},30000);
</script>
</body>
</html>
)rawliteral";

const char* personasPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Personas Registradas</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:20px;max-width:800px;margin:0 auto}
h1{color:#333;text-align:center;margin-bottom:15px}
.item{background:#f5f5f5;padding:12px;margin:8px 0;border-left:4px solid #667eea;border-radius:6px}
.item-nombre{font-size:16px;font-weight:bold;color:#333;margin-bottom:4px}
.item-info{font-size:12px;color:#666}
button{width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-top:10px;color:white;background:#667eea}
button:hover{background:#5568c0}
.btn-success{background:#4CAF50;margin-top:0;margin-bottom:15px}
.btn-success:hover{background:#45a049}
.empty{text-align:center;padding:40px;color:#999;font-style:italic}
</style>
</head>
<body>
<div class="container">
<h1>Personas Registradas</h1>
<button class="btn-success" onclick="window.location.href='/register'">Registrar Nueva Persona</button>
<div id="lista">Cargando...</div>
<button onclick="window.location.href='/gestion'">Volver</button>
</div>
<script>
async function cargar(){
try{
const r=await fetch('/api/personas');
const personas=await r.json();
const lista=document.getElementById('lista');
if(personas.length===0){
lista.innerHTML='<div class="empty">No hay personas registradas</div>';
return;
}
let html='';
personas.forEach(p=>{
html+=`<div class="item">
<div class="item-nombre">${p.nombre}</div>
<div class="item-info">RUT: ${p.rut || 'N/A'} | Email: ${p.email || 'N/A'}</div>
<div class="item-info">Huella ID: ${p.huella_id} | ID Sistema: ${p.id}</div>
</div>`;
});
lista.innerHTML=html;
}catch(e){
document.getElementById('lista').innerHTML='<div class="empty">Error cargando datos</div>';
}
}
cargar();
setInterval(cargar,10000);
</script>
</body>
</html>
)rawliteral";

const char* asistenciasPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Asistencias Registradas</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:20px;max-width:800px;margin:0 auto}
h1{color:#333;text-align:center;margin-bottom:15px}
.item{background:#f5f5f5;padding:12px;margin:8px 0;border-left:4px solid #4CAF50;border-radius:6px}
.item.salida{border-left-color:#ff9800}
.item-nombre{font-size:16px;font-weight:bold;color:#333;margin-bottom:4px}
.item-info{font-size:12px;color:#666}
.badge{display:inline-block;padding:4px 10px;border-radius:12px;font-size:11px;font-weight:bold;color:white;margin-left:5px}
.badge-entrada{background:#4CAF50}
.badge-salida{background:#ff9800}
button{width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-top:10px;color:white;background:#667eea}
button:hover{background:#5568c0}
.empty{text-align:center;padding:40px;color:#999;font-style:italic}
.count{text-align:center;padding:10px;background:#f9f9f9;border-radius:8px;margin-bottom:15px}
</style>
</head>
<body>
<div class="container">
<h1>Registro de Asistencias</h1>
<div class="count" id="count">Total: <strong>0</strong></div>
<div id="lista">Cargando...</div>
<button onclick="window.location.href='/'">Volver</button>
</div>
<script>
async function cargar(){
try{
const r=await fetch('/api/asistencias');
const asistencias=await r.json();
document.getElementById('count').innerHTML=`Total: <strong>${asistencias.length}</strong>`;
const lista=document.getElementById('lista');
if(asistencias.length===0){
lista.innerHTML='<div class="empty">No hay asistencias registradas</div>';
return;
}
let html='';
asistencias.reverse().forEach(a=>{
const clase=a.tipo==='entrada'?'':'salida';
const badge=a.tipo==='entrada'?'badge-entrada':'badge-salida';
html+=`<div class="item ${clase}">
<div class="item-nombre">${a.nombre} <span class="badge ${badge}">${a.tipo.toUpperCase()}</span></div>
<div class="item-info">Timestamp: ${a.timestamp} | ID: ${a.persona_id}</div>
</div>`;
});
lista.innerHTML=html;
}catch(e){
document.getElementById('lista').innerHTML='<div class="empty">Error cargando datos</div>';
}
}
cargar();
setInterval(cargar,10000);
</script>
</body>
</html>
)rawliteral";

const char* turnosPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Gestion de Turnos</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:20px;max-width:800px;margin:0 auto}
h1{color:#333;text-align:center;margin-bottom:15px}
h2{color:#667eea;font-size:18px;margin:15px 0 10px 0;border-bottom:2px solid #667eea;padding-bottom:5px}
.section{background:#f9f9f9;padding:15px;border-radius:8px;margin-bottom:15px}
input{width:100%;padding:10px;border:2px solid #ddd;border-radius:6px;font-size:14px;margin:5px 0}
button{width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-bottom:8px;color:white}
.btn-primary{background:#667eea}
.btn-primary:hover{background:#5568c0}
.btn-success{background:#4CAF50}
.btn-success:hover{background:#45a049}
.item{padding:10px;margin:8px 0;background:white;border-left:4px solid #667eea;border-radius:6px;font-size:13px}
.item strong{display:block;margin-bottom:4px;color:#333}
.item small{color:#666}
.status{text-align:center;padding:10px;margin:10px 0;border-radius:6px;background:#f5f5f5}
</style>
</head>
<body>
<div class="container">
<h1>Gestion de Turnos</h1>

<div class="section">
<h2>Crear Nuevo Turno</h2>
<input id="turnoNombre" placeholder="Nombre del turno (ej: Turno Mañana)">
<input id="turnoInicio" type="time" value="08:00">
<input id="turnoFin" type="time" value="16:00">
<input id="turnoDias" placeholder="Dias: L,M,X,J,V,S,D" value="L,M,X,J,V">
<button class="btn-success" onclick="crearTurno()">Crear Turno</button>
</div>

<div class="section">
<h2>Turnos Existentes</h2>
<div id="listaTurnos">Cargando...</div>
</div>

<button class="btn-primary" onclick="window.location.href='/gestion'">Volver</button>
<div class="status" id="status"></div>
</div>

<script>
async function cargarTurnos(){
try{
const r=await fetch('/api/turnos');
const turnos=await r.json();
const lista=document.getElementById('listaTurnos');
if(turnos.length===0){
lista.innerHTML='<div style="text-align:center;color:#999;padding:20px">No hay turnos creados</div>';
return;
}
let html='';
turnos.forEach(t=>{
html+=`<div class="item">
<strong>${t.nombre}</strong>
<small>${t.inicio} - ${t.fin} | ${t.dias} | ID: ${t.id}</small>
</div>`;
});
lista.innerHTML=html;
}catch(e){
document.getElementById('listaTurnos').innerHTML='Error';
}
}

async function crearTurno(){
const nombre=document.getElementById('turnoNombre').value;
const inicio=document.getElementById('turnoInicio').value;
const fin=document.getElementById('turnoFin').value;
const dias=document.getElementById('turnoDias').value;
if(!nombre||!inicio||!fin){
alert('Complete todos los campos');
return;
}
try{
const r=await fetch(`/crear_turno?nombre=${encodeURIComponent(nombre)}&inicio=${inicio}&fin=${fin}&dias=${encodeURIComponent(dias)}`);
const msg=await r.text();
document.getElementById('status').innerHTML=msg;
if(msg.includes('creado')){
document.getElementById('turnoNombre').value='';
cargarTurnos();
}
}catch(e){
document.getElementById('status').innerHTML='Error: '+e.message;
}
}

cargarTurnos();
setInterval(cargarTurnos,15000);
</script>
</body>
</html>
)rawliteral";

const char* asignacionesPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Gestion de Asignaciones</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:20px;max-width:800px;margin:0 auto}
h1{color:#333;text-align:center;margin-bottom:15px}
h2{color:#667eea;font-size:18px;margin:15px 0 10px 0;border-bottom:2px solid #667eea;padding-bottom:5px}
.section{background:#f9f9f9;padding:15px;border-radius:8px;margin-bottom:15px}
select{width:100%;padding:10px;border:2px solid #ddd;border-radius:6px;font-size:14px;margin:5px 0}
button{width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-bottom:8px;color:white}
.btn-primary{background:#667eea}
.btn-primary:hover{background:#5568c0}
.btn-warning{background:#ff9800}
.btn-warning:hover{background:#f57c00}
.item{padding:10px;margin:8px 0;background:white;border-left:4px solid #ff9800;border-radius:6px;font-size:13px}
.item strong{display:block;margin-bottom:4px;color:#333}
.item small{color:#666}
.status{text-align:center;padding:10px;margin:10px 0;border-radius:6px;background:#f5f5f5}
</style>
</head>
<body>
<div class="container">
<h1>Gestion de Asignaciones</h1>

<div class="section">
<h2>Asignar Turno a Persona</h2>
<select id="selectPersona">
<option value="">Cargando personas...</option>
</select>
<select id="selectTurno">
<option value="">Cargando turnos...</option>
</select>
<button class="btn-warning" onclick="asignarTurno()">Asignar Turno</button>
</div>

<div class="section">
<h2>Asignaciones Actuales</h2>
<div id="listaAsignaciones">Cargando...</div>
</div>

<button class="btn-primary" onclick="window.location.href='/gestion'">Volver</button>
<div class="status" id="status"></div>
</div>

<script>
let personas=[];
let turnos=[];

async function cargarPersonas(){
try{
const r=await fetch('/api/personas');
personas=await r.json();
const select=document.getElementById('selectPersona');
select.innerHTML='<option value="">Seleccione persona...</option>';
personas.forEach(p=>{
select.innerHTML+=`<option value="${p.id}">${p.nombre}</option>`;
});
}catch(e){}
}

async function cargarTurnos(){
try{
const r=await fetch('/api/turnos');
turnos=await r.json();
const select=document.getElementById('selectTurno');
select.innerHTML='<option value="">Seleccione turno...</option>';
turnos.forEach(t=>{
select.innerHTML+=`<option value="${t.id}">${t.nombre} (${t.inicio}-${t.fin})</option>`;
});
}catch(e){}
}

async function cargarAsignaciones(){
try{
const r=await fetch('/api/asignaciones');
const asignaciones=await r.json();
const lista=document.getElementById('listaAsignaciones');
if(asignaciones.length===0){
lista.innerHTML='<div style="text-align:center;color:#999;padding:20px">No hay asignaciones</div>';
return;
}
let html='';
asignaciones.forEach(a=>{
const persona=personas.find(p=>p.id===a.persona_id);
const turno=turnos.find(t=>t.id===a.turno_id);
const nombrePersona=persona?persona.nombre:'ID '+a.persona_id;
const nombreTurno=turno?turno.nombre:'ID '+a.turno_id;
html+=`<div class="item">
<strong>${nombrePersona} -> ${nombreTurno}</strong>
<small>Persona ID: ${a.persona_id} | Turno ID: ${a.turno_id}</small>
</div>`;
});
lista.innerHTML=html;
}catch(e){
document.getElementById('listaAsignaciones').innerHTML='Error';
}
}

async function asignarTurno(){
const persona=document.getElementById('selectPersona').value;
const turno=document.getElementById('selectTurno').value;
if(!persona||!turno){
alert('Seleccione persona y turno');
return;
}
try{
const r=await fetch(`/asignar?persona=${persona}&turno=${turno}`);
const msg=await r.text();
document.getElementById('status').innerHTML=msg;
if(msg.includes('asignado')){
cargarAsignaciones();
}
}catch(e){
document.getElementById('status').innerHTML='Error: '+e.message;
}
}

cargarPersonas();
cargarTurnos();
cargarAsignaciones();
setInterval(()=>{cargarPersonas();cargarTurnos();cargarAsignaciones();},15000);
</script>
</body>
</html>
)rawliteral";

// ======================= SETUP ===========================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\nESP32 Sistema de Asistencia Offline");
  Serial.println("========================================");
  
  FingerSerial.begin(57600, SERIAL_8N1, 13, 12);
  finger.begin(57600);
  
  if (finger.verifyPassword()) {
    Serial.println("Sensor de huellas conectado");
  } else {
    Serial.println("Sensor de huellas NO detectado");
    Serial.println("Verifique las conexiones:");
    Serial.println("   RX (amarillo) -> GPIO 13");
    Serial.println("   TX (blanco)   -> GPIO 12");
    Serial.println("   VCC (rojo)    -> 5V");
    Serial.println("   GND (negro)   -> GND");
  }
  
  initSPIFFS();
  loadWiFiConfig();
  
  WiFi.mode(WIFI_AP);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);
  WiFi.softAP(apSSID, apPASS, 1, 0, 4);
  
  IPAddress local_IP(192,168,4,1);
  IPAddress gateway(192,168,4,1);
  IPAddress subnet(255,255,255,0);
  WiFi.softAPConfig(local_IP, gateway, subnet);
  
  Serial.println("\nPunto de Acceso WiFi:");
  Serial.printf("   SSID: %s\n", apSSID);
  Serial.printf("   Pass: %s\n", apPASS);
  Serial.printf("   IP:   %s\n", WiFi.softAPIP().toString().c_str());
  Serial.printf("   Canal: 1\n");
  Serial.printf("   Potencia: MAXIMA (19.5dBm)\n\n");

  server.on("/", []() { server.send(200, "text/html", htmlPage); });
  server.on("/register", []() { server.send(200, "text/html", registerPage); });
  server.on("/gestion", []() { server.send(200, "text/html", gestionPage); });
  server.on("/personas", []() { server.send(200, "text/html", personasPage); });
  server.on("/asistencias", []() { server.send(200, "text/html", asistenciasPage); });
  server.on("/turnos", []() { server.send(200, "text/html", turnosPage); });
  server.on("/asignaciones", []() { server.send(200, "text/html", asignacionesPage); });
  server.on("/wifi-setup", []() { server.send(200, "text/html", wifiConfigPage); });
  server.on("/wifi-config", handleWiFiConfig);
  server.on("/registrar", handleRegisterUser);
  server.on("/crear_turno", handleCreateTurn);
  server.on("/asignar", handleAssignTurn);
  server.on("/marcar", handleMarcarAsistencia);
  server.on("/api/personas", handleGetPersonas);
  server.on("/api/turnos", handleGetTurnos);
  server.on("/api/asignaciones", handleGetAsignaciones);
  server.on("/api/asistencias", handleGetAsistencias);
  server.on("/limpiar", handleLimpiarDatos);

  server.begin();
  Serial.println("Servidor web iniciado");
  Serial.println("Acceda desde: http://" + WiFi.softAPIP().toString());
  Serial.println("\n========================================");
  Serial.println("Sistema listo para usar");
}

// ======================= LOOP ============================
void loop() {
  server.handleClient();
  
  if (millis() - lastFingerCheck >= FINGER_CHECK_INTERVAL) {
    lastFingerCheck = millis();
    
    int p = finger.getImage();
    if (p == FINGERPRINT_OK) {
      p = finger.image2Tz();
      if (p == FINGERPRINT_OK) {
        p = finger.fingerSearch();
        if (p == FINGERPRINT_OK && finger.fingerID > 0) {
          int huellaID = finger.fingerID;
          
          if (huellaID != lastFingerID || (millis() - lastFingerTime) > FINGER_DEBOUNCE) {
            lastFingerID = huellaID;
            lastFingerTime = millis();
            
            Serial.printf("\nHuella detectada: ID %d\n", huellaID);
            String resultado = registrarAsistenciaAutomatica(huellaID);
            Serial.println(resultado);
            Serial.println("----------------------------------------\n");
            
            delay(500);
          }
        }
      }
    }
  }
}
