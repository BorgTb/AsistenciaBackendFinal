#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include <base64.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "img_converters.h"
#include "fb_gfx.h"
#include "esp_timer.h"

// ======= CONFIGURACIÓN DE LA CÁMARA AI THINKER =======
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ======= CONFIGURACIÓN WIFI Y MQTT =======
const char* ssid = "Casa_Meza";
const char* password = "18351835";
const char* mqtt_server = "192.168.1.2"; // IP de tu broker MQTT
const int mqtt_port = 1883;
const char* api_server = "http://192.168.1.2:5000/api"; // URL de la API backend

// ======= OBJETOS GLOBALES =======
WiFiClient espClient;
PubSubClient client(espClient);
WebServer server(80);

// Variables de detección
unsigned long lastDetectionTime = 0;
const unsigned long detectionInterval = 3000; // Detectar cada 3 segundos
const int brightnessThreshold = 50; // Umbral de brillo para detectar movimiento/presencia
bool autoDetectionEnabled = false; // Control de detección automática
String lastResponse = "Sistema listo para registrar rostros"; // Última respuesta del servidor

// ======= HTML CON REGISTRO =======
// ======= HTML PRINCIPAL CON MENÚ =======
const char* htmlPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ESP32-CAM Control Panel</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:20px;max-width:600px;margin:0 auto}
h1{color:#333;margin-bottom:5px;font-size:22px;text-align:center}
.subtitle{color:#666;text-align:center;margin-bottom:15px;font-size:12px}
.tabs{display:flex;gap:5px;margin-bottom:15px;border-bottom:2px solid #e0e0e0}
.tab{padding:10px 15px;background:none;border:none;border-bottom:3px solid transparent;cursor:pointer;font-size:13px;font-weight:600;color:#666;flex:1}
.tab:hover{color:#667eea}
.tab.active{color:#667eea;border-bottom-color:#667eea}
.tab-content{display:none;animation:fadeIn 0.3s}
.tab-content.active{display:block}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.input-group{margin-bottom:15px}
label{display:block;color:#333;font-weight:600;margin-bottom:5px;font-size:13px}
input,select{width:100%;padding:10px;border:2px solid #e0e0e0;border-radius:8px;font-size:14px}
input:focus,select:focus{outline:none;border-color:#667eea}
button{width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-bottom:8px}
.btn-primary{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white}
.btn-success{background:#4CAF50;color:white}
.btn-warning{background:#ff9800;color:white}
.btn-danger{background:#f44336;color:white}
.status{background:#f5f5f5;padding:12px;border-radius:8px;margin-top:10px;text-align:center;min-height:50px;display:flex;align-items:center;justify-content:center;font-size:13px}
.list{max-height:300px;overflow-y:auto;margin-top:10px}
.list-item{background:#f8f9fa;padding:12px;margin-bottom:8px;border-radius:8px;border-left:4px solid #667eea}
.list-item strong{display:block;color:#333;margin-bottom:5px}
.list-item small{color:#666;font-size:12px}
.badge{display:inline-block;padding:3px 8px;border-radius:12px;font-size:11px;background:#e0e0e0;margin-left:5px}
.loading{text-align:center;padding:20px;color:#666}
</style>
</head>
<body>
<div class="container">
<h1>📷 ESP32-CAM Control Panel</h1>
<p class="subtitle">Sistema de Gestión Integrado</p>

<div class="tabs">
<button class="tab active" onclick="switchTab('registro')">📝 Registro</button>
<button class="tab" onclick="switchTab('personas')">👥 Personas</button>
<button class="tab" onclick="switchTab('turnos')">🕐 Turnos</button>
<button class="tab" onclick="switchTab('asignar')">➕ Asignar</button>
</div>

<!-- TAB REGISTRO -->
<div id="tab-registro" class="tab-content active">
<div class="input-group">
<label for="nombre">Nombre:</label>
<input type="text" id="nombre" placeholder="Ej: Juan Perez">
</div>
<button class="btn-primary" onclick="registrarRostro()">📷 Registrar Rostro</button>
<button class="btn-success" onclick="toggleDeteccion()">🔍 Detección Auto</button>
<div class="status" id="status">Sistema listo</div>
</div>

<!-- TAB PERSONAS -->
<div id="tab-personas" class="tab-content">
<button class="btn-primary" onclick="cargarPersonas()">🔄 Actualizar</button>
<div id="listaPersonas" class="list loading">Cargando...</div>
</div>

<!-- TAB TURNOS -->
<div id="tab-turnos" class="tab-content">
<button class="btn-primary" onclick="cargarTurnos()">🔄 Actualizar</button>
<div id="listaTurnos" class="list loading">Cargando...</div>
</div>

<!-- TAB ASIGNAR -->
<div id="tab-asignar" class="tab-content">
<div class="input-group">
<label>Persona:</label>
<select id="selPersona"><option>Cargando...</option></select>
</div>
<div class="input-group">
<label>Turno:</label>
<select id="selTurno"><option>Cargando...</option></select>
</div>
<button class="btn-success" onclick="asignarTurno()">✅ Asignar Turno</button>
<div class="status" id="statusAsignar"></div>
</div>
</div>

<script>
const API='http://192.168.1.2:5000/api';
let autoDetectActive=false;

setInterval(async()=>{
try{
const r=await fetch('/status');
const t=await r.text();
if(t && !document.getElementById('status').innerHTML.includes('Capturando')){
document.getElementById('status').innerHTML=t;
}
}catch(e){}
},2000);

function switchTab(tab){
document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
event.target.classList.add('active');
document.getElementById('tab-'+tab).classList.add('active');
if(tab==='personas')cargarPersonas();
if(tab==='turnos')cargarTurnos();
if(tab==='asignar')cargarOpciones();
}

async function registrarRostro(){
const nombre=document.getElementById('nombre').value.trim();
const status=document.getElementById('status');
if(!nombre){status.innerHTML='⚠️ Ingresa un nombre';return;}
status.innerHTML='📸 Capturando...';
try{
const r=await fetch('/register?nombre='+encodeURIComponent(nombre));
const t=await r.text();
status.innerHTML=r.ok?'✅ '+t:'❌ '+t;
document.getElementById('nombre').value='';
}catch(e){status.innerHTML='❌ Error';}
}

async function toggleDeteccion(){
try{
const r=await fetch('/auto-detect');
const t=await r.text();
autoDetectActive=t.includes('activada');
document.getElementById('status').innerHTML=t;
}catch(e){}
}

async function cargarPersonas(){
const div=document.getElementById('listaPersonas');
div.innerHTML='<div class="loading">Cargando...</div>';
try{
const r=await fetch(API+'/personas');
const data=await r.json();
if(data.success && data.personas.length>0){
let html='';
data.personas.forEach(p=>{
html+=`<div class="list-item"><strong>${p.nombre}</strong><small>Registrado: ${p.fecha_registro}<span class="badge">${p.total_imagenes} fotos</span></small></div>`;
});
div.innerHTML=html;
}else{
div.innerHTML='<div class="loading">No hay personas</div>';
}
}catch(e){div.innerHTML='<div class="loading">Error: '+e.message+'</div>';}
}

async function cargarTurnos(){
const div=document.getElementById('listaTurnos');
div.innerHTML='<div class="loading">Cargando...</div>';
try{
const r=await fetch(API+'/turnos');
const data=await r.json();
if(data.success && data.turnos.length>0){
let html='';
data.turnos.forEach(t=>{
html+=`<div class="list-item"><strong>${t.nombre_turno}</strong><small>${t.hora_inicio} - ${t.hora_fin}<span class="badge">${t.dias_semana}</span></small></div>`;
});
div.innerHTML=html;
}else{
div.innerHTML='<div class="loading">No hay turnos</div>';
}
}catch(e){div.innerHTML='<div class="loading">Error: '+e.message+'</div>';}
}

async function cargarOpciones(){
try{
const [personas,turnos]=await Promise.all([
fetch(API+'/personas').then(r=>r.json()),
fetch(API+'/turnos').then(r=>r.json())
]);
const selP=document.getElementById('selPersona');
const selT=document.getElementById('selTurno');
selP.innerHTML='<option value="">-- Seleccionar --</option>';
selT.innerHTML='<option value="">-- Seleccionar --</option>';
if(personas.success)personas.personas.forEach(p=>selP.innerHTML+=`<option value="${p.id}">${p.nombre}</option>`);
if(turnos.success)turnos.turnos.forEach(t=>selT.innerHTML+=`<option value="${t.id}">${t.nombre_turno} (${t.hora_inicio}-${t.hora_fin})</option>`);
}catch(e){console.error(e);}
}

async function asignarTurno(){
const personaId=document.getElementById('selPersona').value;
const turnoId=document.getElementById('selTurno').value;
const status=document.getElementById('statusAsignar');
if(!personaId || !turnoId){status.innerHTML='⚠️ Selecciona persona y turno';return;}
try{
const r=await fetch(API+'/asignaciones',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({persona_id:personaId,turno_id:turnoId})
});
const data=await r.json();
status.innerHTML=data.success?'✅ '+data.message:'❌ '+data.error;
}catch(e){status.innerHTML='❌ Error: '+e.message;}
}

document.getElementById('nombre').addEventListener('keypress',e=>{if(e.key==='Enter')registrarRostro();});
</script>
</body>
</html>
)rawliteral";

// ======= DETECCIÓN SIMPLE DE PRESENCIA =======
bool detectPresence(camera_fb_t *fb) {
  // Análisis simple: verificar que haya suficiente contraste/cambio en la imagen
  // Esto detecta si hay algo frente a la cámara (persona, movimiento, etc.)
  
  if (!fb || fb->len < 100) {
    return false;
  }

  // Analizar muestra de píxeles del centro de la imagen
  uint32_t sum = 0;
  uint32_t sampleSize = min(1000, (int)fb->len);
  uint32_t step = fb->len / sampleSize;
  
  for (uint32_t i = 0; i < fb->len; i += step) {
    sum += fb->buf[i];
  }
  
  uint32_t avg = sum / sampleSize;
  
  // Si el promedio está en un rango razonable, asumimos que hay algo/alguien
  // (no está completamente negro ni completamente blanco)
  bool hasContent = (avg > 40 && avg < 235);
  
  if (hasContent) {
    Serial.printf("✅ Contenido detectado (promedio: %d)\n", avg);
  }
  
  return hasContent;
}

// ======= CAPTURA Y ENVÍO MQTT CON NOMBRE =======
void sendImageMQTT(String personName = "", bool modoAsistencia = false) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Error al capturar imagen");
    return;
  }

  String topicStart, topicPart, topicEnd;
  
  if (modoAsistencia) {
    // MODO ASISTENCIA: para reconocimiento automático
    topicStart = "test/asistencia/start";
    topicPart = "test/asistencia/part";
    topicEnd = "test/asistencia/end";
    Serial.println("� Modo: ASISTENCIA (reconocimiento automático)");
  } else {
    // MODO REGISTRO: con nombre específico
    if (personName.length() == 0) personName = "agustin";
    topicStart = "test/registro/" + personName + "/start";
    topicPart = "test/registro/" + personName + "/part";
    topicEnd = "test/registro/" + personName + "/end";
    Serial.printf("📸 Modo: REGISTRO (persona: %s)\n", personName.c_str());
  }

  // Publicar inicio
  client.publish(topicStart.c_str(), "START");

  // Convertir a Base64
  String encoded = base64::encode(fb->buf, fb->len);
  const size_t chunkSize = 2000; // 2 KB por bloque
  for (size_t i = 0; i < encoded.length(); i += chunkSize) {
    String part = encoded.substring(i, i + chunkSize);
    client.publish(topicPart.c_str(), part.c_str());
    delay(10); // pequeño delay para no saturar
  }

  // Publicar fin
  bool ok = client.publish(topicEnd.c_str(), "END");
  if (ok) {
    Serial.println("✅ Fin publicado: END");
    if (!modoAsistencia) {
      Serial.printf("📤 Imagen enviada para: %s\n", personName.c_str());
    } else {
      Serial.println("📤 Imagen enviada para reconocimiento");
    }
  } else {
    Serial.println("❌ Falló publicación de END");
    Serial.print("Estado cliente MQTT: ");
    Serial.println(client.state());
  }

  esp_camera_fb_return(fb);
  Serial.println("✅ Imagen enviada por MQTT");
}

// ======= HANDLERS WEB =======
void handleRoot() {
  server.send(200, "text/html", htmlPage);
}

void handleRegister() {
  if (!server.hasArg("nombre")) {
    server.send(400, "text/plain", "❌ Falta el parámetro 'nombre'");
    return;
  }
  
  String nombre = server.arg("nombre");
  nombre.trim();
  
  if (nombre.length() == 0) {
    server.send(400, "text/plain", "❌ El nombre no puede estar vacío");
    return;
  }
  
  // Sanitizar nombre (solo alfanuméricos y espacios)
  String nombreLimpio = "";
  for (int i = 0; i < nombre.length(); i++) {
    char c = nombre.charAt(i);
    if (isalnum(c) || c == ' ' || c == '_') {
      nombreLimpio += c;
    }
  }
  
  if (nombreLimpio.length() == 0) {
    server.send(400, "text/plain", "❌ Nombre inválido");
    return;
  }
  
  Serial.printf("\n📝 REGISTRO MANUAL SOLICITADO: %s\n", nombreLimpio.c_str());
  
  // 🔴 CAPTURAR Y ENVIAR INMEDIATAMENTE (sin verificar detección automática)
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Error al capturar imagen");
    server.send(500, "text/plain", "❌ Error al capturar imagen");
    return;
  }

  Serial.println("👤 Capturando para registro manual...");

  // Construir tópicos con el nombre de la persona
  String topicStart = "test/registro/" + nombreLimpio + "/start";
  String topicPart = "test/registro/" + nombreLimpio + "/part";
  String topicEnd = "test/registro/" + nombreLimpio + "/end";

  // Publicar inicio
  client.publish(topicStart.c_str(), "START");

  // Convertir a Base64
  String encoded = base64::encode(fb->buf, fb->len);
  const size_t chunkSize = 2000;
  for (size_t i = 0; i < encoded.length(); i += chunkSize) {
    String part = encoded.substring(i, i + chunkSize);
    client.publish(topicPart.c_str(), part.c_str());
    delay(10);
  }

  // Publicar fin
  client.publish(topicEnd.c_str(), "END");
  esp_camera_fb_return(fb);
  
  Serial.printf("✅ Imagen enviada para: %s\n", nombreLimpio.c_str());
  server.send(200, "text/plain", "✅ Rostro de " + nombreLimpio + " enviado para registro");
}

void handleAutoDetect() {
  autoDetectionEnabled = !autoDetectionEnabled; // Toggle on/off
  lastDetectionTime = 0; // Resetear para detección inmediata
  
  if (autoDetectionEnabled) {
    Serial.println("🔍 Detección automática ACTIVADA");
    server.send(200, "text/plain", "✅ Detección automática activada");
  } else {
    Serial.println("⏸️ Detección automática DESACTIVADA");
    server.send(200, "text/plain", "⏸️ Detección automática desactivada");
  }
}

void handleStatus() {
  server.send(200, "text/html", lastResponse);
}

void handleCapture() {
  // Usar modo asistencia si está activada la detección
  sendImageMQTT("", autoDetectionEnabled);
  server.send(200, "text/plain", "✅ Imagen capturada y enviada por MQTT");
}

// ======= CONEXIONES =======
void setupWifi() {
  WiFi.begin(ssid, password);
  Serial.print("Conectando a WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ Conectado a WiFi");
  Serial.println(WiFi.localIP());
}

void reconnectMQTT() {
  while (!client.connected()) {
    Serial.print("Conectando a MQTT...");
    if (client.connect("ESP32CAM_Sender")) {
      Serial.println("Conectado!");
      // Suscribirse al topic de respuestas
      client.subscribe("test/respuesta/#");
      Serial.println("Suscrito a test/respuesta/#");
    } else {
      Serial.print("Falla, rc=");
      Serial.println(client.state());
      delay(2000);
    }
  }
}

// ======= SETUP =======
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Convertir payload a string
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  // Parsear el mensaje: formato "STATUS|MENSAJE"
  int separatorIndex = message.indexOf('|');
  if (separatorIndex > 0) {
    String status = message.substring(0, separatorIndex);
    String msg = message.substring(separatorIndex + 1);
    
    // Formatear respuesta según el estado
    if (status == "REGISTRADO") {
      lastResponse = "<span style='color: #4CAF50;'>✅ " + msg + "</span>";
    } else if (status == "DUPLICADO") {
      lastResponse = "<span style='color: #FF9800;'>⚠️ " + msg + "</span>";
    } else if (status == "ERROR") {
      lastResponse = "<span style='color: #f44336;'>❌ " + msg + "</span>";
    } else if (status == "ASISTENCIA") {
      lastResponse = "<span style='color: #2196F3;'>✅ " + msg + "</span>";
    } else if (status == "SIN_TURNO") {
      lastResponse = "<span style='color: #FF9800;'>⚠️ " + msg + "</span>";
    } else {
      lastResponse = msg;
    }
  } else {
    lastResponse = message;
  }
  
  Serial.println("Respuesta recibida: " + lastResponse);
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);

  // Config cámara
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 10;
  config.fb_count = 1;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("❌ Error al iniciar cámara");
    return;
  }

  setupWifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(mqttCallback);
  reconnectMQTT();

  server.on("/", handleRoot);
  server.on("/register", handleRegister);
  server.on("/auto-detect", handleAutoDetect);
  server.on("/status", handleStatus);
  server.on("/capture", handleCapture);
  server.begin();
  Serial.println("🌐 Servidor web iniciado");
  Serial.println("� Sistema de registro de rostros activo");
  Serial.println("⏸️ Detección automática DESACTIVADA (usar botón para activar)");
  Serial.print("🌐 Accede a: http://");
  Serial.println(WiFi.localIP());
}

// ======= LOOP =======
void loop() {
  if (!client.connected()) {
    reconnectMQTT();
  }
  client.loop();
  server.handleClient();

  // 🔍 DETECCIÓN AUTOMÁTICA (solo si está activada)
  if (autoDetectionEnabled) {
    unsigned long currentTime = millis();
    if (currentTime - lastDetectionTime >= detectionInterval) {
      lastDetectionTime = currentTime;
      
      // Capturar frame para detección
      camera_fb_t *fb = esp_camera_fb_get();
      if (fb) {
        Serial.println("🔍 Escaneando presencia...");
        bool hasPresence = detectPresence(fb);
        
        if (hasPresence) {
          Serial.println("👤 ¡PRESENCIA DETECTADA! Enviando imagen...");
          esp_camera_fb_return(fb); // Liberar el frame de detección
          sendImageMQTT("", true); // Enviar en modo asistencia (reconocimiento)
        } else {
          Serial.println("⚪ Sin presencia detectada");
          esp_camera_fb_return(fb);
        }
      }
    }
  }
}
