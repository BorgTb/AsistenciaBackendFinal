#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <base64.h>

// ===== Pines cámara AI Thinker =====
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

String wifiSSID = "";
String wifiPASS = "";

// ===== MQTT =====
const char* mqtt_server = "192.168.1.2";
const int mqtt_port = 1883;
const char* topic_base = "test/imagenes";
const char* topic_recognition = "test/reconocimiento";  // ✅ NUEVO: Resultado de reconocimiento

WiFiClient espClient;
PubSubClient client(espClient);
WebServer server(80);
Preferences prefs;
bool camera_ok = false;
unsigned long lastMqttAttempt = 0;
const unsigned long mqttRetryInterval = 10000;

// ===== Detección de cambio MEJORADA =====
uint8_t* last_frame = nullptr;
size_t last_frame_size = 0;
unsigned long last_send_time = 0;
const unsigned long send_interval = 2000;  // Enviar máximo cada 2 segundos
const size_t MAX_FRAME_SIZE = 100000;  // Máximo tamaño de frame esperado

bool hasSignificantChange(camera_fb_t *fb) {
  if (!fb || !fb->buf || fb->len == 0) {
    Serial.println("❌ Frame inválido");
    return false;
  }

  unsigned long now = millis();
  
  // No enviar muy frecuentemente
  if (now - last_send_time < send_interval) {
    return false;
  }

  // ===== Primera imagen =====
  if (!last_frame) {
    // Validar tamaño
    if (fb->len > MAX_FRAME_SIZE) {
      Serial.printf("❌ Frame demasiado grande: %u bytes\n", fb->len);
      return false;
    }

    last_frame = (uint8_t*)malloc(fb->len);
    if (!last_frame) {
      Serial.println("❌ Error: no hay memoria para guardar frame");
      return false;
    }

    memcpy(last_frame, fb->buf, fb->len);
    last_frame_size = fb->len;
    last_send_time = now;
    Serial.printf("✅ Primera imagen guardada: %u bytes\n", fb->len);
    return true;
  }

  // ===== Comparar tamaño =====
  int diff = abs((int)fb->len - (int)last_frame_size);
  int threshold = last_frame_size * 15 / 100;  // 15% de diferencia

  if (diff > threshold) {
    Serial.printf("✅ Cambio detectado (diff: %d bytes, threshold: %d)\n", diff, threshold);
    
    // Liberar memoria anterior
    free(last_frame);
    
    // Validar nuevo tamaño
    if (fb->len > MAX_FRAME_SIZE) {
      Serial.printf("❌ Frame demasiado grande: %u bytes\n", fb->len);
      last_frame = nullptr;
      last_frame_size = 0;
      return false;
    }
    
    // Guardar nuevo frame
    last_frame = (uint8_t*)malloc(fb->len);
    if (!last_frame) {
      Serial.println("❌ Error: no hay memoria para nuevo frame");
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

// ===== Inicializar cámara =====
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
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
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
    Serial.printf("❌ Error al iniciar cámara: 0x%x\n", err);
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

// ===== Conexión WiFi =====
void tryConnectWiFi() {
  prefs.begin("wifiCreds", true);
  wifiSSID = prefs.getString("ssid", "");
  wifiPASS = prefs.getString("pass", "");
  prefs.end();

  if (wifiSSID == "") {
    Serial.println("⚠️ No hay credenciales guardadas");
    return;
  }

  WiFi.begin(wifiSSID.c_str(), wifiPASS.c_str());
  Serial.printf("Conectando a %s", wifiSSID.c_str());
  for (int i = 0; i < 30; i++) {
    if (WiFi.status() == WL_CONNECTED) break;
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED)
    Serial.println("✅ WiFi conectado: " + WiFi.localIP().toString());
  else
    Serial.println("❌ Falló conexión WiFi");
}

void startAP() {
  WiFi.softAP(apSSID, apPASS);
  IPAddress IP = WiFi.softAPIP();
  Serial.printf("📡 AP activo: %s  IP: %s\n", apSSID, IP.toString().c_str());
}

// ===== MQTT =====
void reconnectMQTT() {
  if (client.connected()) return;
  
  int intentos = 0;
  const int maxIntentos = 5;
  
  while (!client.connected() && intentos < maxIntentos) {
    Serial.printf("🔄 Conectando a MQTT (%d/%d)...", intentos + 1, maxIntentos);
    
    if (client.connect("ESP32CAM_Client")) {
      Serial.println("✅ Conectado a MQTT");
      return;
    } else {
      Serial.printf(" ❌ Error: %d\n", client.state());
      intentos++;
      delay(2000);
    }
  }
  
  if (!client.connected()) {
    Serial.println("❌ No se pudo conectar a MQTT");
  }
}

// ===== Callback MQTT para recibir resultados de reconocimiento =====
void onMessageReceived(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  
  Serial.printf("📨 Resultado recibido: %s\n", msg.c_str());
  // Aquí podrías hacer algo con el resultado (parpadear LED, etc)
}

// ===== Envío por fragmentos MEJORADO =====
void enviarImagenFragmentada() {
  if (!client.connected()) {
    Serial.println("❌ No conectado a MQTT");
    return;
  }
  if (!camera_ok) startCamera();

  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Error capturando imagen");
    return;
  }

  // ===== DETECTAR CAMBIO ANTES DE ENVIAR =====
  if (!hasSignificantChange(fb)) {
    Serial.println("⏭️ Sin cambios significativos");
    esp_camera_fb_return(fb);
    return;
  }

  String sessionId = String(millis() / 1000);
  
  String topic_start = String(topic_base) + "/" + sessionId + "/start";
  String topic_part  = String(topic_base) + "/" + sessionId + "/part";
  String topic_end   = String(topic_base) + "/" + sessionId + "/end";

  Serial.printf("📤 Sesión: %s | Tamaño: %u bytes\n", sessionId.c_str(), fb->len);

  // Codificar con validación
  String imageBase64;
  try {
    imageBase64 = base64::encode(fb->buf, fb->len);
  } catch (...) {
    Serial.println("❌ Error codificando base64");
    esp_camera_fb_return(fb);
    return;
  }

  int total = imageBase64.length();
  if (total == 0) {
    Serial.println("❌ Base64 vacío");
    esp_camera_fb_return(fb);
    return;
  }

  int chunkSize = 1024;

  // ===== Enviar inicio =====
  if (!client.publish(topic_start.c_str(), "start")) {
    Serial.println("❌ Error publicando /start");
    esp_camera_fb_return(fb);
    return;
  }
  Serial.printf("✅ Inicio enviado\n");
  delay(50);

  // ===== Enviar fragmentos =====
  int fragmento = 0;
  for (int i = 0; i < total; i += chunkSize) {
    int endPos = min(i + chunkSize, total);
    String part = imageBase64.substring(i, endPos);
    
    if (part.length() == 0) {
      Serial.printf("❌ Fragmento %d vacío\n", fragmento);
      continue;
    }

    if (!client.publish(topic_part.c_str(), part.c_str())) {
      Serial.printf("❌ Fragmento %d fallido\n", fragmento);
    } else {
      Serial.printf("✅ Fragmento %d/%d (%d bytes)\n", 
        fragmento + 1, (total + chunkSize - 1) / chunkSize, part.length());
    }
    
    fragmento++;
    delay(10);
  }

  // ===== Enviar fin =====
  if (!client.publish(topic_end.c_str(), "end")) {
    Serial.println("❌ Error publicando /end");
  } else {
    Serial.printf("✅ Transmisión completada\n");
  }

  esp_camera_fb_return(fb);
}

// ===== Envío para registro de rostro =====
void enviarParaRegistro(String personName) {
  if (!client.connected()) {
    Serial.println("❌ No conectado a MQTT");
    return;
  }
  if (!camera_ok) startCamera();

  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Error capturando imagen");
    return;
  }

  // Construir tópicos de registro
  String topic_start = "test/registro/" + personName + "/start";
  String topic_part  = "test/registro/" + personName + "/part";
  String topic_end   = "test/registro/" + personName + "/end";

  Serial.printf("📤 Registrando a: %s | Tamaño: %u bytes\n", personName.c_str(), fb->len);

  // Codificar
  String imageBase64 = base64::encode(fb->buf, fb->len);
  int total = imageBase64.length();
  
  if (total == 0) {
    Serial.println("❌ Base64 vacío");
    esp_camera_fb_return(fb);
    return;
  }

  int chunkSize = 1024;

  // Enviar inicio
  if (!client.publish(topic_start.c_str(), "start")) {
    Serial.println("❌ Error publicando /start");
    esp_camera_fb_return(fb);
    return;
  }
  Serial.printf("✅ Inicio de registro enviado\n");
  delay(50);

  // Enviar fragmentos
  for (int i = 0; i < total; i += chunkSize) {
    int endPos = min(i + chunkSize, total);
    String part = imageBase64.substring(i, endPos);
    
    if (part.length() > 0) {
      client.publish(topic_part.c_str(), part.c_str());
    }
    delay(10);
  }

  // Enviar fin
  client.publish(topic_end.c_str(), "end");
  esp_camera_fb_return(fb);
  
  Serial.printf("✅ Persona registrada: %s\n", personName.c_str());
}

// ===== STREAM MJPEG =====
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
  Serial.println("🔴 Stream desconectado");
}

// ===== Captura única =====
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

// ===== Página principal =====
void handleRoot() {
  String wifiStatus = (WiFi.status() == WL_CONNECTED) ? "✅ Conectado" : "❌ Desconectado";
  String mqttStatus = client.connected() ? "✅ Conectado" : "❌ Desconectado";
  String cameraStatus = camera_ok ? "✅ Iniciada" : "❌ Error";
  
  String html = R"rawliteral(
  <!DOCTYPE html>
  <html>
  <head>
    <title>ESP32-CAM Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
      body { background:#101010; color:#0ff; font-family:Arial; text-align:center; padding:20px; }
      .status { background:#1a1a1a; border-radius:8px; padding:15px; margin:10px 0; border-left:4px solid #0099ff; }
      .status-item { display:flex; justify-content:space-between; padding:8px 0; }
      button { background:#0099ff; border:none; color:white; padding:12px 24px; border-radius:6px; margin:8px; font-size:16px; cursor:pointer; transition:0.3s; }
      button:hover { background:#0077cc; transform:scale(1.05); }
      button:active { transform:scale(0.95); }
      .container { max-width:600px; margin:0 auto; }
      h2 { color:#0099ff; }
      .section { margin:20px 0; }
    </style>
  </head>
  <body>
    <div class="container">
      <h2>📷 Sistema Asistencia - ESP32-CAM</h2>
      
      <div class="status">
        <h3>Estado</h3>
        <div class="status-item"><span>WiFi:</span><strong>)rawliteral" + wifiStatus + R"rawliteral(</strong></div>
        <div class="status-item"><span>MQTT:</span><strong>)rawliteral" + mqttStatus + R"rawliteral(</strong></div>
        <div class="status-item"><span>Cámara:</span><strong>)rawliteral" + cameraStatus + R"rawliteral(</strong></div>
        <div class="status-item"><span>IP:</span><strong>)rawliteral" + WiFi.localIP().toString() + R"rawliteral(</strong></div>
      </div>

      <div class="section">
        <h3>🎯 Reconocimiento</h3>
        <button onclick="window.location.href='/recognize'">🎥 Reconocer Rostro</button>
        <button onclick="window.location.href='/capture'">📸 Foto</button>
      </div>

      <div class="section">
        <h3>� Registro de Rostros</h3>
        <button onclick="window.location.href='/register'">✏️ Registrar Persona</button>
      </div>

      <div class="section">
        <h3>⚙️ Configuración</h3>
        <button onclick="window.location.href='/video'">🎥 Ver Video</button>
        <button onclick="window.location.href='/wifi'">🌐 WiFi</button>
      </div>
    </div>
  </body>
  </html>
  )rawliteral";
  server.send(200, "text/html", html);
}

void handleVideoPage() {
  server.send(200, "text/html", "<img src='/stream' style='width:100%;'>");
}

// ===== Página de reconocimiento (VIDEO + BOTÓN ENVIAR) =====
void handleRecognize() {
  String html = R"rawliteral(
  <html>
  <head>
    <title>Reconocer Rostro</title>
    <style>
      body { background:#101010; color:#0ff; font-family:Arial; text-align:center; padding:20px; }
      img { width:100%; max-width:640px; border:2px solid #0099ff; border-radius:8px; }
      button { background:#00cc00; border:none; color:white; padding:15px 30px; border-radius:6px; margin:15px; font-size:18px; cursor:pointer; }
      button:hover { background:#009900; }
      .container { max-width:700px; margin:0 auto; }
    </style>
  </head>
  <body>
    <div class="container">
      <h2>🎯 Reconocer Rostro</h2>
      <img src='/stream'>
      <br>
      <button onclick="reconocer()">✅ Reconocer</button>
      <button onclick="window.location.href='/'">⬅ Volver</button>
    </div>
    <script>
      function reconocer() {
        alert('Capturando y enviando...');
        fetch('/do_recognize').then(r => r.text()).then(msg => {
          alert(msg);
        });
      }
    </script>
  </body>
  </html>
  )rawliteral";
  server.send(200, "text/html", html);
}

// ===== Página de registro (VIDEO + INPUT NOMBRE + BOTÓN REGISTRAR) =====
void handleRegister() {
  String html = R"rawliteral(
  <html>
  <head>
    <title>Registrar Persona</title>
    <style>
      body { background:#101010; color:#0ff; font-family:Arial; text-align:center; padding:20px; }
      img { width:100%; max-width:640px; border:2px solid #ff9900; border-radius:8px; }
      input { padding:10px; font-size:16px; width:80%; margin:10px 0; }
      button { background:#ff9900; border:none; color:white; padding:15px 30px; border-radius:6px; margin:15px; font-size:18px; cursor:pointer; }
      button:hover { background:#cc7700; }
      .container { max-width:700px; margin:0 auto; }
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
      <button onclick="window.location.href='/'">⬅ Volver</button>
    </div>
    <script>
      function registrar() {
        const nombre = document.getElementById('personName').value;
        if (!nombre || nombre.trim() === '') {
          alert('Por favor ingresa un nombre');
          return;
        }
        alert('Capturando y registrando a: ' + nombre);
        fetch('/do_register?name=' + encodeURIComponent(nombre))
          .then(r => r.text())
          .then(msg => { alert(msg); });
      }
    </script>
  </body>
  </html>
  )rawliteral";
  server.send(200, "text/html", html);
}

void handleWifiPage() {
  String html = R"rawliteral(
  <html><body style='text-align:center;'>
  <h3>Configuración WiFi</h3>
  <form method='POST' action='/save'>
    <input name='ssid' placeholder='SSID' required><br>
    <input name='pass' type='password' placeholder='Password' required><br>
    <button type='submit'>Guardar</button>
  </form>
  <a href='/'>⬅ Volver</a>
  </body></html>)rawliteral";
  server.send(200, "text/html", html);
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

void handleSendMQTT() {
  if (WiFi.status() != WL_CONNECTED) {
    server.send(500, "text/html", "<h3>❌ WiFi no conectado</h3><a href='/'>Volver</a>");
    return;
  }
  
  if (!client.connected()) {
    reconnectMQTT();
  }
  
  if (!client.connected()) {
    server.send(500, "text/html", "<h3>❌ MQTT no conectado</h3><a href='/'>Volver</a>");
    return;
  }

  enviarImagenFragmentada();
  server.send(200, "text/html", "<h3>✅ Imagen enviada.</h3><a href='/'>Volver</a>");
}

// ===== Handler para reconocer =====
void handleDoRecognize() {
  if (WiFi.status() != WL_CONNECTED) {
    server.send(500, "text/plain", "❌ WiFi no conectado");
    return;
  }
  
  if (!client.connected()) {
    reconnectMQTT();
  }
  
  if (!client.connected()) {
    server.send(500, "text/plain", "❌ MQTT no conectado");
    return;
  }

  enviarImagenFragmentada();
  server.send(200, "text/plain", "✅ Rostro enviado para reconocimiento");
}

// ===== Handler para registrar =====
void handleDoRegister() {
  if (WiFi.status() != WL_CONNECTED) {
    server.send(500, "text/plain", "❌ WiFi no conectado");
    return;
  }
  
  if (!client.connected()) {
    reconnectMQTT();
  }
  
  if (!client.connected()) {
    server.send(500, "text/plain", "❌ MQTT no conectado");
    return;
  }

  // Obtener nombre de la persona
  if (!server.hasArg("name")) {
    server.send(400, "text/plain", "❌ Nombre no proporcionado");
    return;
  }

  String personName = server.arg("name");
  Serial.printf("📝 Registrando: %s\n", personName.c_str());
  
  enviarParaRegistro(personName);
  server.send(200, "text/plain", "✅ Persona '" + personName + "' registrada");
}

// ===== Setup =====
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n🚀 Iniciando ESP32-CAM...");
  
  startCamera();
  tryConnectWiFi();
  if (WiFi.status() != WL_CONNECTED) startAP();

  server.on("/", handleRoot);
  server.on("/video", handleVideoPage);
  server.on("/recognize", handleRecognize);
  server.on("/register", handleRegister);
  server.on("/stream", handleStream);
  server.on("/capture", handleCapture);
  server.on("/do_recognize", handleDoRecognize);
  server.on("/do_register", handleDoRegister);
  server.on("/wifi", handleWifiPage);
  server.on("/save", HTTP_POST, handleSave);
  server.on("/send_mqtt", handleSendMQTT);
  server.begin();

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(onMessageReceived);
  
  Serial.println("🌐 Servidor HTTP iniciado");
}

// ===== Loop =====
void loop() {
  server.handleClient();
  
  if (WiFi.status() == WL_CONNECTED) {
    if (!client.connected()) {
      unsigned long now = millis();
      if (now - lastMqttAttempt > mqttRetryInterval) {
        reconnectMQTT();
        lastMqttAttempt = now;
      }
    } else {
      client.loop();
      // ✅ Envío automático cada 2 segundos si detecta cambio
      enviarImagenFragmentada();
    }
  }
  
  delay(100);
}