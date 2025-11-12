#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <base64.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPIFFS.h>
#include "time.h"
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

// ===== AP para configuración =====
const char* apSSID = "ESP32-CAM-SETUP";
const char* apPASS = "12345678";

// ======= CONFIGURACIÓN WIFI Y MQTT =======
String wifiSSID = "";
String wifiPASS = "";
const char* mqtt_server = "192.168.1.2";
const int mqtt_port = 1883;
const char* api_server = "http://192.168.1.2:5000/api";

// NTP Server para obtener hora real
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = -10800; // UTC-3 (Chile/Argentina)
const int daylightOffset_sec = 0;

// ======= OBJETOS GLOBALES =======
WiFiClient espClient;
PubSubClient client(espClient);
WebServer server(80);
Preferences prefs;

// Variables de detección
unsigned long lastDetectionTime = 0;
const unsigned long detectionInterval = 3000;
bool autoDetectionEnabled = false;
String lastResponse = "Sistema listo";
bool camera_ok = false;

// Variables offline
bool isOnline = false;
unsigned long lastSyncAttempt = 0;
const unsigned long syncInterval = 60000; // Intentar sync cada 60 seg
int pendingCount = 0;

// Variables para detección de cambios
uint8_t* last_frame = nullptr;
size_t last_frame_size = 0;
unsigned long last_send_time = 0;
const unsigned long send_interval = 2000;
const size_t MAX_FRAME_SIZE = 100000;

// ======= FUNCIONES SPIFFS =======
void initSPIFFS() {
  if (!SPIFFS.begin(true)) {
    Serial.println("❌ Error montando SPIFFS");
    return;
  }
  Serial.println("✅ SPIFFS montado");
  
  // Mostrar espacio disponible
  size_t total = SPIFFS.totalBytes();
  size_t used = SPIFFS.usedBytes();
  Serial.printf("📊 SPIFFS: %d / %d bytes usados\n", used, total);
  
  // Crear archivo de asistencias si no existe
  if (!SPIFFS.exists("/asistencias.json")) {
    File file = SPIFFS.open("/asistencias.json", "w");
    if (file) {
      file.println("[]");
      file.close();
      Serial.println("✅ Archivo asistencias.json creado");
    }
  }
  
  contarPendientes();
}

void contarPendientes() {
  File file = SPIFFS.open("/asistencias.json", "r");
  if (!file) {
    pendingCount = 0;
    return;
  }
  
  String content = file.readString();
  file.close();
  
  DynamicJsonDocument doc(8192);
  deserializeJson(doc, content);
  JsonArray array = doc.as<JsonArray>();
  pendingCount = array.size();
  
  Serial.printf("📋 Asistencias pendientes: %d\n", pendingCount);
}

void guardarAsistenciaOffline(String nombre, String tipo) {
  // Leer archivo actual
  File file = SPIFFS.open("/asistencias.json", "r");
  if (!file) {
    Serial.println("❌ Error abriendo archivo");
    return;
  }
  
  String content = file.readString();
  file.close();
  
  DynamicJsonDocument doc(8192);
  DeserializationError error = deserializeJson(doc, content);
  
  if (error) {
    Serial.println("❌ Error parseando JSON");
    return;
  }
  
  JsonArray array = doc.as<JsonArray>();
  
  // Agregar nueva asistencia
  JsonObject asistencia = array.createNestedObject();
  asistencia["nombre"] = nombre;
  asistencia["tipo"] = tipo;
  asistencia["fecha_hora"] = getFormattedTime();
  
  // Guardar de vuelta
  file = SPIFFS.open("/asistencias.json", "w");
  if (!file) {
    Serial.println("❌ Error escribiendo archivo");
    return;
  }
  
  serializeJson(doc, file);
  file.close();
  
  pendingCount++;
  Serial.printf("💾 Asistencia guardada offline: %s - %s (total: %d)\n", 
                nombre.c_str(), tipo.c_str(), pendingCount);
}

bool sincronizarAsistencias() {
  if (pendingCount == 0) {
    Serial.println("✅ No hay asistencias pendientes");
    return true;
  }
  
  if (!isOnline) {
    Serial.println("⚠️ Sin conexión para sincronizar");
    return false;
  }
  
  // Leer asistencias pendientes
  File file = SPIFFS.open("/asistencias.json", "r");
  if (!file) {
    Serial.println("❌ Error abriendo archivo");
    return false;
  }
  
  String content = file.readString();
  file.close();
  
  if (content.length() < 3) { // "[]"
    Serial.println("✅ No hay datos para sincronizar");
    return true;
  }
  
  // Enviar al servidor
  HTTPClient http;
  http.begin(String(api_server) + "/asistencias/sync");
  http.addHeader("Content-Type", "application/json");
  
  // Construir JSON de sincronización
  DynamicJsonDocument doc(8192);
  doc["dispositivo_ip"] = WiFi.localIP().toString();
  
  DynamicJsonDocument arrayDoc(8192);
  deserializeJson(arrayDoc, content);
  doc["asistencias"] = arrayDoc.as<JsonArray>();
  
  String jsonStr;
  serializeJson(doc, jsonStr);
  
  Serial.println("📤 Sincronizando asistencias...");
  int httpCode = http.POST(jsonStr);
  
  if (httpCode == 200) {
    String response = http.getString();
    Serial.println("✅ Sincronización exitosa");
    Serial.println(response);
    
    // Limpiar archivo
    file = SPIFFS.open("/asistencias.json", "w");
    file.println("[]");
    file.close();
    
    pendingCount = 0;
    http.end();
    return true;
  } else {
    Serial.printf("❌ Error sincronizando: %d\n", httpCode);
    http.end();
    return false;
  }
}

// ======= DETECCIÓN DE CAMBIOS SIGNIFICATIVOS =======
bool hasSignificantChange(camera_fb_t *fb) {
  if (!fb || !fb->buf || fb->len == 0) {
    Serial.println("ERROR: Frame inválido");
    return false;
  }

  unsigned long now = millis();
  
  if (now - last_send_time < send_interval) {
    return false;
  }

  if (!last_frame) {
    if (fb->len > MAX_FRAME_SIZE) {
      Serial.printf("ERROR: Frame demasiado grande: %u bytes\n", fb->len);
      return false;
    }

    last_frame = (uint8_t*)malloc(fb->len);
    if (!last_frame) {
      Serial.println("ERROR: no hay memoria para guardar frame");
      return false;
    }

    memcpy(last_frame, fb->buf, fb->len);
    last_frame_size = fb->len;
    last_send_time = now;
    Serial.printf("Primera imagen guardada: %u bytes\n", fb->len);
    return true;
  }

  int diff = abs((int)fb->len - (int)last_frame_size);
  int threshold = last_frame_size * 15 / 100;

  if (diff > threshold) {
    Serial.printf("Cambio detectado (diff: %d bytes, threshold: %d)\n", diff, threshold);
    
    free(last_frame);
    
    if (fb->len > MAX_FRAME_SIZE) {
      Serial.printf("ERROR: Frame demasiado grande: %u bytes\n", fb->len);
      last_frame = nullptr;
      last_frame_size = 0;
      return false;
    }
    
    last_frame = (uint8_t*)malloc(fb->len);
    if (!last_frame) {
      Serial.println("ERROR: no hay memoria para nuevo frame");
      last_frame_size = 0;
      return false;
    }

    memcpy(last_frame, fb->buf, fb->len);
    last_frame_size = fb->len;
    last_send_time = now;
    return true;
  }

  return false;
}

// ======= FUNCIONES DE TIEMPO =======
String getFormattedTime() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return "2024-01-01 00:00:00";
  }
  
  char buffer[20];
  strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", &timeinfo);
  return String(buffer);
}

void initTime() {
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  Serial.println("⏰ Sincronizando hora con NTP...");
  
  struct tm timeinfo;
  if (getLocalTime(&timeinfo)) {
    Serial.println("✅ Hora sincronizada: " + getFormattedTime());
  } else {
    Serial.println("⚠️ No se pudo sincronizar hora (trabajará sin timestamp correcto)");
  }
}

// ======= DETECCIÓN DE PRESENCIA =======
bool detectPresence(camera_fb_t *fb) {
  if (!fb || fb->len < 100) return false;
  
  uint32_t sum = 0;
  uint32_t sampleSize = min(1000, (int)fb->len);
  uint32_t step = fb->len / sampleSize;
  
  for (uint32_t i = 0; i < fb->len; i += step) {
    sum += fb->buf[i];
  }
  
  uint32_t avg = sum / sampleSize;
  return (avg > 40 && avg < 235);
}

// ======= INICIALIZAR CÁMARA =======
void startCamera() {
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

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 8;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("ERROR al iniciar cámara: 0x%x\n", err);
    camera_ok = false;
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  s->set_brightness(s, 1);
  s->set_contrast(s, 1);
  s->set_saturation(s, 1);
  s->set_sharpness(s, 1);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);
  s->set_wb_mode(s, 0);
  s->set_exposure_ctrl(s, 1);
  s->set_aec2(s, 1);
  s->set_gainceiling(s, (gainceiling_t)2);
  s->set_lenc(s, 1);
  s->set_raw_gma(s, 1);
  s->set_colorbar(s, 0);

  camera_ok = true;
  Serial.println("✅ Cámara inicializada");
}

// ======= CONFIGURACIÓN WIFI CON PREFERENCES =======
void tryConnectWiFi() {
  prefs.begin("wifiCreds", true);
  wifiSSID = prefs.getString("ssid", "");
  wifiPASS = prefs.getString("pass", "");
  prefs.end();

  if (wifiSSID == "") {
    Serial.println("No hay credenciales guardadas");
    return;
  }

  WiFi.begin(wifiSSID.c_str(), wifiPASS.c_str());
  Serial.printf("Conectando a %s", wifiSSID.c_str());
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("✅ WiFi conectado: " + WiFi.localIP().toString());
    isOnline = true;
  } else {
    Serial.println("⚠️ Fallo conexión WiFi");
    isOnline = false;
  }
}

void startAP() {
  WiFi.softAP(apSSID, apPASS);
  IPAddress IP = WiFi.softAPIP();
  Serial.printf("📡 AP activo: %s  IP: %s\n", apSSID, IP.toString().c_str());
}

// ======= ENVÍO MQTT =======
void sendImageMQTT(String personName = "", bool modoAsistencia = false) {
  if (!camera_ok) startCamera();
  
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Error al capturar imagen");
    return;
  }

  String topicStart, topicPart, topicEnd;
  
  if (modoAsistencia) {
    topicStart = "test/asistencia/start";
    topicPart = "test/asistencia/part";
    topicEnd = "test/asistencia/end";
  } else {
    if (personName.length() == 0) personName = "agustin";
    topicStart = "test/registro/" + personName + "/start";
    topicPart = "test/registro/" + personName + "/part";
    topicEnd = "test/registro/" + personName + "/end";
  }

  client.publish(topicStart.c_str(), "START");

  String encoded = base64::encode(fb->buf, fb->len);
  const size_t chunkSize = 2000;
  for (size_t i = 0; i < encoded.length(); i += chunkSize) {
    String part = encoded.substring(i, i + chunkSize);
    client.publish(topicPart.c_str(), part.c_str());
    delay(10);
  }

  client.publish(topicEnd.c_str(), "END");
  esp_camera_fb_return(fb);
}

// ======= STREAM MJPEG =======
void handleStream() {
  if (!camera_ok) startCamera();
  WiFiClient clientHTTP = server.client();
  if (!clientHTTP.connected()) return;

  clientHTTP.println("HTTP/1.1 200 OK");
  clientHTTP.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  clientHTTP.println("Access-Control-Allow-Origin: *");
  clientHTTP.println();

  while (clientHTTP.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) continue;
    clientHTTP.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
    clientHTTP.write(fb->buf, fb->len);
    clientHTTP.print("\r\n");
    esp_camera_fb_return(fb);
    delay(30);
  }

  clientHTTP.stop();
  Serial.println("Stream desconectado");
}

// ======= CAPTURA ÚNICA =======
void handleCapture() {
  if (!camera_ok) startCamera();
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(500, "text/plain", "Error al capturar");
    return;
  }

  WiFiClient clientHTTP = server.client();
  clientHTTP.println("HTTP/1.1 200 OK");
  clientHTTP.println("Content-Type: image/jpeg");
  clientHTTP.printf("Content-Length: %u\r\n\r\n", fb->len);
  clientHTTP.write(fb->buf, fb->len);
  clientHTTP.print("\r\n");
  esp_camera_fb_return(fb);
}

// ======= HTML CON MODO OFFLINE =======
const char* htmlPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ESP32-CAM Control Offline</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}
.container{background:white;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.3);padding:20px;max-width:600px;margin:0 auto}
h1{color:#333;text-align:center;margin-bottom:10px}
.status-bar{background:#f5f5f5;padding:10px;border-radius:8px;margin-bottom:15px;text-align:center}
.status-item{display:flex;justify-content:space-between;padding:6px 0}
.online{color:#4CAF50;font-weight:bold}
.offline{color:#f44336;font-weight:bold}
button{width:100%;padding:12px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;margin-bottom:8px;color:white;transition:0.3s}
button:hover{transform:scale(1.02)}
button:active{transform:scale(0.98)}
.btn-primary{background:#667eea}
.btn-success{background:#4CAF50}
.btn-warning{background:#ff9800}
.btn-danger{background:#f44336}
.btn-info{background:#00bcd4}
.status{background:#f5f5f5;padding:12px;border-radius:8px;margin-top:10px;text-align:center;min-height:50px;display:flex;align-items:center;justify-content:center;font-size:13px}
.badge{display:inline-block;padding:5px 10px;border-radius:12px;font-size:12px;background:#e0e0e0;margin:5px}
.section{margin:15px 0;padding:10px;background:#f9f9f9;border-radius:8px}
h3{color:#667eea;margin-bottom:8px;font-size:16px}
</style>
</head>
<body>
<div class="container">
<h1>📷 ESP32-CAM Sistema Asistencia</h1>
<div class="status-bar">
<div class="status-item"><span>🔌 Conexión:</span><span id="connectionStatus">Verificando...</span></div>
<div class="status-item"><span>📊 Pendientes:</span><span class="badge" id="pendingBadge">0</span></div>
<div class="status-item"><span>📹 Cámara:</span><strong>Activa</strong></div>
</div>

<div class="section">
<h3>🎯 Reconocimiento</h3>
<button class="btn-success" onclick="toggleDeteccion()">🔍 Toggle Detección Auto</button>
<button class="btn-primary" onclick="window.location.href='/recognize'">🎥 Reconocer Rostro</button>
<button class="btn-info" onclick="window.location.href='/capture'">📸 Foto</button>
</div>

<div class="section">
<h3>👤 Registro</h3>
<button class="btn-warning" onclick="window.location.href='/register'">✏️ Registrar Persona</button>
</div>

<div class="section">
<h3>⚙️ Sistema</h3>
<button class="btn-warning" onclick="syncNow()">🔄 Sincronizar</button>
<button class="btn-primary" onclick="checkStatus()">📊 Info Sistema</button>
<button class="btn-danger" onclick="window.location.href='/wifi'">🌐 Config WiFi</button>
</div>

<div class="status" id="status">Sistema listo</div>
</div>
<script>
setInterval(async()=>{
try{
const r=await fetch('/status');
const data=await r.json();
document.getElementById('status').innerHTML=data.mensaje;
document.getElementById('connectionStatus').innerHTML=data.online?'🟢 ONLINE':'🔴 OFFLINE';
document.getElementById('connectionStatus').className=data.online?'online':'offline';
document.getElementById('pendingBadge').innerHTML=data.pendientes;
}catch(e){}
},2000);
async function toggleDeteccion(){
try{
const r=await fetch('/auto-detect');
const t=await r.text();
document.getElementById('status').innerHTML=t;
}catch(e){document.getElementById('status').innerHTML='❌ Error';}
}
async function syncNow(){
try{
document.getElementById('status').innerHTML='🔄 Sincronizando...';
const r=await fetch('/sync');
const t=await r.text();
document.getElementById('status').innerHTML=t;
}catch(e){document.getElementById('status').innerHTML='❌ Error sincronizando';}
}
async function checkStatus(){
try{
const r=await fetch('/info');
const data=await r.json();
let msg='<strong>Información del Sistema:</strong><br>';
msg+='IP: '+data.ip+'<br>';
msg+='Uptime: '+data.uptime+'s<br>';
msg+='RAM libre: '+data.free_heap+' bytes<br>';
msg+='SPIFFS: '+data.spiffs_used+'/'+data.spiffs_total+' bytes';
document.getElementById('status').innerHTML=msg;
}catch(e){document.getElementById('status').innerHTML='❌ Error';}
}
</script>
</body>
</html>
)rawliteral";

// ===== PÁGINA DE RECONOCIMIENTO =====
const char* recognizePage = R"rawliteral(
<html>
<head>
<title>Reconocer Rostro</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{background:#101010;color:#0ff;font-family:Arial;text-align:center;padding:20px}
img{width:100%;max-width:640px;border:2px solid #0099ff;border-radius:8px}
button{background:#00cc00;border:none;color:white;padding:15px 30px;border-radius:6px;margin:15px;font-size:18px;cursor:pointer}
button:hover{background:#009900}
.back{background:#667eea}
.back:hover{background:#5568c0}
.container{max-width:700px;margin:0 auto}
</style>
</head>
<body>
<div class="container">
<h2>🎯 Reconocer Rostro</h2>
<img src='/stream'>
<br>
<button onclick="reconocer()">✅ Reconocer</button>
<button class="back" onclick="window.location.href='/'">⬅ Volver</button>
</div>
<script>
function reconocer(){
alert('Capturando y enviando...');
fetch('/do_recognize').then(r=>r.text()).then(msg=>{alert(msg);});
}
</script>
</body>
</html>
)rawliteral";

// ===== PÁGINA DE REGISTRO =====
const char* registerPage = R"rawliteral(
<html>
<head>
<title>Registrar Persona</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{background:#101010;color:#0ff;font-family:Arial;text-align:center;padding:20px}
img{width:100%;max-width:640px;border:2px solid #ff9900;border-radius:8px}
input{padding:10px;font-size:16px;width:80%;margin:10px 0;border-radius:6px;border:2px solid #ff9900}
button{background:#ff9900;border:none;color:white;padding:15px 30px;border-radius:6px;margin:15px;font-size:18px;cursor:pointer}
button:hover{background:#cc7700}
.back{background:#667eea}
.back:hover{background:#5568c0}
.container{max-width:700px;margin:0 auto}
</style>
</head>
<body>
<div class="container">
<h2>👤 Registrar Persona</h2>
<img src='/stream'>
<br>
<input type="text" id="personName" placeholder="Nombre de la persona" autofocus>
<br>
<button onclick="registrar()">✅ Registrar</button>
<button class="back" onclick="window.location.href='/'">⬅ Volver</button>
</div>
<script>
function registrar(){
const nombre=document.getElementById('personName').value;
if(!nombre||nombre.trim()===''){
alert('Por favor ingresa un nombre');
return;
}
alert('Capturando y registrando a: '+nombre);
fetch('/do_register?name='+encodeURIComponent(nombre)).then(r=>r.text()).then(msg=>{alert(msg);});
}
</script>
</body>
</html>
)rawliteral";

// ===== PÁGINA DE CONFIGURACIÓN WIFI =====
const char* wifiPage = R"rawliteral(
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Configurar WiFi</title>
<style>
body{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);font-family:Arial;text-align:center;padding:40px}
.container{background:white;border-radius:15px;padding:30px;max-width:400px;margin:0 auto;box-shadow:0 10px 30px rgba(0,0,0,0.3)}
h3{color:#333;margin-bottom:20px}
input{width:100%;padding:12px;margin:10px 0;border:2px solid #ddd;border-radius:6px;font-size:16px}
button{width:100%;background:#667eea;color:white;border:none;padding:15px;border-radius:6px;font-size:18px;cursor:pointer;margin-top:10px}
button:hover{background:#5568c0}
a{display:block;margin-top:15px;color:#667eea;text-decoration:none}
a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="container">
<h3>🌐 Configuración WiFi</h3>
<form method='POST' action='/save'>
<input name='ssid' placeholder='SSID' required>
<input name='pass' type='password' placeholder='Password' required>
<button type='submit'>💾 Guardar y Reiniciar</button>
</form>
<a href='/'>⬅ Volver</a>
</div>
</body>
</html>
)rawliteral";

// ======= HANDLERS WEB =======
void handleRoot() {
  server.send(200, "text/html", htmlPage);
}

void handleRecognize() {
  server.send(200, "text/html", recognizePage);
}

void handleRegister() {
  server.send(200, "text/html", registerPage);
}

void handleWifiPage() {
  server.send(200, "text/html", wifiPage);
}

void handleSave() {
  String ssid = server.arg("ssid");
  String pass = server.arg("pass");
  prefs.begin("wifiCreds", false);
  prefs.putString("ssid", ssid);
  prefs.putString("pass", pass);
  prefs.end();
  server.send(200, "text/html", "<h3>✅ Guardado. Reiniciando...</h3>");
  delay(1000);
  ESP.restart();
}

void handleDoRecognize() {
  if (!isOnline) {
    server.send(500, "text/plain", "⚠️ Sin conexión - Esperando red");
    return;
  }
  
  if (!client.connected()) {
    reconnectMQTT();
  }
  
  if (!client.connected()) {
    server.send(500, "text/plain", "❌ MQTT no conectado");
    return;
  }

  sendImageMQTT("", true);
  server.send(200, "text/plain", "✅ Rostro enviado para reconocimiento");
}

void handleDoRegister() {
  if (!isOnline) {
    server.send(500, "text/plain", "⚠️ Sin conexión - Esperando red");
    return;
  }
  
  if (!client.connected()) {
    reconnectMQTT();
  }
  
  if (!client.connected()) {
    server.send(500, "text/plain", "❌ MQTT no conectado");
    return;
  }

  if (!server.hasArg("name")) {
    server.send(400, "text/plain", "❌ Nombre no proporcionado");
    return;
  }

  String personName = server.arg("name");
  Serial.printf("Registrando: %s\n", personName.c_str());
  
  sendImageMQTT(personName, false);
  server.send(200, "text/plain", "✅ Persona '" + personName + "' registrada");
}

void handleStatus() {
  DynamicJsonDocument doc(512);
  doc["online"] = isOnline;
  doc["pendientes"] = pendingCount;
  doc["mensaje"] = lastResponse;
  
  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

void handleAutoDetect() {
  autoDetectionEnabled = !autoDetectionEnabled;
  lastDetectionTime = 0;
  
  String msg = autoDetectionEnabled ? "✅ Detección automática activada" : "⏸️ Detección automática desactivada";
  Serial.println(msg);
  server.send(200, "text/plain", msg);
}

void handleSync() {
  if (sincronizarAsistencias()) {
    server.send(200, "text/plain", "✅ Sincronización exitosa");
  } else {
    server.send(500, "text/plain", "❌ Error en sincronización");
  }
}

void handleInfo() {
  DynamicJsonDocument doc(512);
  doc["ip"] = WiFi.localIP().toString();
  doc["uptime"] = millis() / 1000;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["spiffs_total"] = SPIFFS.totalBytes();
  doc["spiffs_used"] = SPIFFS.usedBytes();
  doc["pendientes"] = pendingCount;
  
  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

// ======= MQTT CALLBACK =======
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  int separatorIndex = message.indexOf('|');
  if (separatorIndex > 0) {
    String status = message.substring(0, separatorIndex);
    String msg = message.substring(separatorIndex + 1);
    
    // Parsear respuesta de asistencia
    if (status == "ASISTENCIA") {
      // Formato: "nombre: ENTRADA registrada - Turno Mañana"
      int colonIndex = msg.indexOf(':');
      if (colonIndex > 0) {
        String nombre = msg.substring(0, colonIndex);
        String resto = msg.substring(colonIndex + 1);
        
        // Determinar tipo
        String tipo = resto.indexOf("ENTRADA") >= 0 ? "entrada" : "salida";
        
        // Si estamos online, ya se registró en el servidor
        // Si estamos offline, guardar localmente
        if (!isOnline) {
          guardarAsistenciaOffline(nombre, tipo);
          lastResponse = "💾 Guardado offline: " + msg;
        } else {
          lastResponse = "✅ " + msg;
        }
      }
    } else if (status == "SIN_TURNO") {
      lastResponse = "⚠️ " + msg;
    } else if (status == "ERROR") {
      lastResponse = "❌ " + msg;
    } else {
      lastResponse = msg;
    }
  }
  
  Serial.println("Respuesta: " + lastResponse);
}

// ======= SETUP WIFI =======
void setupWifi() {
  WiFi.begin(ssid, password);
  Serial.print("Conectando a WiFi");
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi conectado");
    Serial.println(WiFi.localIP());
    isOnline = true;
  } else {
    Serial.println("\n⚠️ WiFi no conectado - MODO OFFLINE");
    isOnline = false;
  }
}

void reconnectMQTT() {
  if (!isOnline) return;
  
  if (!client.connected()) {
    Serial.print("Conectando a MQTT...");
    if (client.connect("ESP32CAM_Offline")) {
      Serial.println("✅ Conectado a MQTT");
      client.subscribe("test/respuesta/#");
    } else {
      Serial.printf("❌ Falla MQTT, rc=%d\n", client.state());
      isOnline = false;
    }
  }
}

// ======= SETUP =======
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n🚀 Iniciando ESP32-CAM Sistema Asistencia Offline...");
  
  // Iniciar SPIFFS primero
  initSPIFFS();
  
  // Iniciar cámara
  startCamera();
  
  // Intentar conectar WiFi
  tryConnectWiFi();
  
  // Si no hay WiFi, iniciar AP
  if (WiFi.status() != WL_CONNECTED) {
    startAP();
    isOnline = false;
  }
  
  // Configurar hora si hay internet
  if (isOnline) {
    initTime();
    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(mqttCallback);
    reconnectMQTT();
  }

  // Configurar servidor web
  server.on("/", handleRoot);
  server.on("/recognize", handleRecognize);
  server.on("/register", handleRegister);
  server.on("/stream", handleStream);
  server.on("/capture", handleCapture);
  server.on("/do_recognize", handleDoRecognize);
  server.on("/do_register", handleDoRegister);
  server.on("/wifi", handleWifiPage);
  server.on("/save", HTTP_POST, handleSave);
  server.on("/status", handleStatus);
  server.on("/auto-detect", handleAutoDetect);
  server.on("/sync", handleSync);
  server.on("/info", handleInfo);
  server.begin();
  
  Serial.println("🌐 Servidor web iniciado");
  Serial.println("🔌 Modo: " + String(isOnline ? "ONLINE" : "OFFLINE"));
  Serial.print("🌐 Accede a: http://");
  if (isOnline) {
    Serial.println(WiFi.localIP());
  } else {
    Serial.println(WiFi.softAPIP());
  }
}

// ======= LOOP =======
void loop() {
  // Verificar conexión WiFi
  if (WiFi.status() == WL_CONNECTED && !isOnline) {
    Serial.println("🔌 Conexión recuperada");
    isOnline = true;
    initTime();
    reconnectMQTT();
    sincronizarAsistencias(); // Intentar sync inmediato
  } else if (WiFi.status() != WL_CONNECTED && isOnline) {
    Serial.println("❌ Conexión perdida - MODO OFFLINE");
    isOnline = false;
  }
  
  // MQTT
  if (isOnline) {
    if (!client.connected()) {
      reconnectMQTT();
    }
    client.loop();
  }
  
  server.handleClient();
  
  // Sync periódico
  if (isOnline && pendingCount > 0) {
    unsigned long now = millis();
    if (now - lastSyncAttempt >= syncInterval) {
      lastSyncAttempt = now;
      sincronizarAsistencias();
    }
  }
  
  // Detección automática
  if (autoDetectionEnabled) {
    unsigned long currentTime = millis();
    if (currentTime - lastDetectionTime >= detectionInterval) {
      lastDetectionTime = currentTime;
      
      camera_fb_t *fb = esp_camera_fb_get();
      if (fb) {
        bool hasPresence = detectPresence(fb);
        
        if (hasPresence) {
          Serial.println("👤 ¡PRESENCIA DETECTADA!");
          esp_camera_fb_return(fb);
          
          if (isOnline) {
            // Enviar por MQTT para reconocimiento
            sendImageMQTT("", true);
          } else {
            // Modo offline: guardar con timestamp local
            // (requeriría reconocimiento local o simplemente logging)
            Serial.println("⚠️ OFFLINE - No se puede procesar reconocimiento");
            lastResponse = "⚠️ Offline - Esperando conexión";
          }
        } else {
          esp_camera_fb_return(fb);
        }
      }
    }
  }
}
