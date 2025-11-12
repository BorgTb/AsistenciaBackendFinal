#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <PubSubClient.h>
#include <base64.h>
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
const char* htmlPage = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ESP32-CAM Sistema de Registro</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { 
  font-family: 'Segoe UI', Arial, sans-serif; 
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
}
.container {
  background: white;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  padding: 40px;
  max-width: 500px;
  width: 100%;
}
h1 { 
  color: #333; 
  margin-bottom: 10px;
  font-size: 28px;
  text-align: center;
}
.subtitle {
  color: #666;
  text-align: center;
  margin-bottom: 30px;
  font-size: 14px;
}
.input-group {
  margin-bottom: 25px;
}
label {
  display: block;
  color: #333;
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 14px;
}
input[type="text"] {
  width: 100%;
  padding: 12px 15px;
  border: 2px solid #e0e0e0;
  border-radius: 10px;
  font-size: 16px;
  transition: border 0.3s;
}
input[type="text"]:focus {
  outline: none;
  border-color: #667eea;
}
button {
  width: 100%;
  padding: 15px;
  border: none;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  margin-bottom: 10px;
}
.btn-register {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}
.btn-register:hover {
  transform: translateY(-2px);
  box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
}
.btn-detect {
  background: #4CAF50;
  color: white;
}
.btn-detect:hover {
  background: #45a049;
  transform: translateY(-2px);
}
.status {
  background: #f5f5f5;
  padding: 15px;
  border-radius: 10px;
  margin-top: 20px;
  text-align: center;
  min-height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.status-text {
  color: #333;
  font-size: 14px;
}
.icon { margin-right: 8px; }
.warning { color: #ff9800; }
.success { color: #4CAF50; }
.error { color: #f44336; }
</style>
</head>
<body>
<div class="container">
  <h1>📷 Sistema de Registro</h1>
  <p class="subtitle">ESP32-CAM Face Recognition</p>
  
  <div class="input-group">
    <label for="nombre">Nombre de la persona:</label>
    <input type="text" id="nombre" placeholder="Ej: Juan Perez" autocomplete="off">
  </div>
  
  <button class="btn-register" onclick="registrarRostro()">
    <span class="icon">�</span> Registrar Nuevo Rostro
  </button>
  
  <button class="btn-detect" onclick="activarDeteccion()">
    <span class="icon">🔍</span> Activar Detección Automática
  </button>
  
  <div class="status">
    <p class="status-text" id="status">Sistema listo para registrar rostros</p>
  </div>
</div>

<script>
// Actualizar estado desde el servidor cada 2 segundos
setInterval(async () => {
  try {
    const response = await fetch('/status');
    const text = await response.text();
    if (text && !document.getElementById('status').innerHTML.includes('Capturando')) {
      document.getElementById('status').innerHTML = text;
    }
  } catch (error) {
    // Silenciar errores de polling
  }
}, 2000);

async function registrarRostro() {
  const nombre = document.getElementById('nombre').value.trim();
  const statusEl = document.getElementById('status');
  
  if (!nombre) {
    statusEl.innerHTML = '<span class="error">⚠️ Por favor ingresa un nombre</span>';
    return;
  }
  
  statusEl.innerHTML = '<span class="warning">📸 Capturando imagen...</span>';
  
  try {
    const response = await fetch('/register?nombre=' + encodeURIComponent(nombre));
    const text = await response.text();
    
    if (response.ok) {
      statusEl.innerHTML = '<span class="success">' + text + '</span>';
      document.getElementById('nombre').value = '';
      
      // Esperar respuesta del servidor (máximo 5 segundos)
      let attempts = 0;
      const checkStatus = setInterval(async () => {
        try {
          const statusResponse = await fetch('/status');
          const statusText = await statusResponse.text();
          if (statusText && statusText !== '' && !statusText.includes('listo')) {
            statusEl.innerHTML = statusText;
            clearInterval(checkStatus);
          }
          attempts++;
          if (attempts >= 10) { // 10 intentos = 5 segundos
            clearInterval(checkStatus);
          }
        } catch (e) {
          // Silenciar errores
        }
      }, 500);
    } else {
      statusEl.innerHTML = '<span class="error">' + text + '</span>';
    }
  } catch (error) {
    statusEl.innerHTML = '<span class="error">❌ Error de conexión</span>';
  }
}

async function activarDeteccion() {
  const statusEl = document.getElementById('status');
  const btn = event.target;
  
  statusEl.innerHTML = '<span class="warning">⏳ Procesando...</span>';
  
  try {
    const response = await fetch('/auto-detect');
    const text = await response.text();
    
    if (text.includes('activada')) {
      statusEl.innerHTML = '<span class="success">✅ Detección automática ACTIVADA</span>';
      btn.innerHTML = '<span class="icon">⏸️</span> Desactivar Detección';
      btn.style.background = '#ff9800';
    } else {
      statusEl.innerHTML = '<span class="warning">⏸️ Detección automática DESACTIVADA</span>';
      btn.innerHTML = '<span class="icon">🔍</span> Activar Detección Automática';
      btn.style.background = '#4CAF50';
    }
  } catch (error) {
    statusEl.innerHTML = '<span class="error">❌ Error al cambiar detección</span>';
  }
}

// Enter para registrar
document.getElementById('nombre').addEventListener('keypress', function(e) {
  if (e.key === 'Enter') registrarRostro();
});
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
void sendImageMQTT(String personName = "agustin") {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Error al capturar imagen");
    return;
  }

  // 🔍 DETECTAR PRESENCIA ANTES DE ENVIAR
  Serial.println("🔍 Verificando presencia...");
  bool hasPresence = detectPresence(fb);
  
  if (!hasPresence) {
    Serial.println("⚠️ No se detectó presencia. Imagen NO enviada.");
    esp_camera_fb_return(fb);
    return;
  }

  Serial.println("👤 ¡Presencia detectada! Enviando imagen...");

  // Construir tópicos con el nombre de la persona
  String topicStart = "test/registro/" + personName + "/start";
  String topicPart = "test/registro/" + personName + "/part";
  String topicEnd = "test/registro/" + personName + "/end";

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
    Serial.printf("📤 Imagen enviada para: %s\n", personName.c_str());
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
  sendImageMQTT();
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
          sendImageMQTT(); // Capturar y enviar nueva imagen
        } else {
          Serial.println("⚪ Sin presencia detectada");
          esp_camera_fb_return(fb);
        }
      }
    }
  }
}
