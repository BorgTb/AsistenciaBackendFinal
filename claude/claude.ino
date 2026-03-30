// ============================================================
// ESP32-CAM Sistema de Asistencia
// Iteraciones 1-4: Offline + Huella + Camara + Backend
// Pines AS608: RX=GPIO14, TX=GPIO15
// ============================================================

#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <Adafruit_Fingerprint.h>
#include <HTTPClient.h>
#include "esp_camera.h"

// ===== Sensor de huellas (RX=GPIO14, TX=GPIO15) =====
HardwareSerial FingerSerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&FingerSerial);

WebServer server(80);

// ===== Configuracion AP =====
const char* apSSID   = "ESP32-ASISTENCIA";
const char* apPASS   = "12345678";
const char* hostname = "esp32-cam-asistencia";

// ===== WiFi externo configurable =====
String savedSSID = "";
String savedPASS = "";
bool   isOnline  = false;

// ===== Backend =====
// Cambia esta IP por la de tu PC cuando estes en modo online
String backendURL     = "http://192.168.1.7:5000";
bool   camaraIniciada = false;

// ===== Timestamp =====
unsigned long bootEpoch = 0;

// ===== Escaneo automatico de huellas =====
unsigned long lastFingerCheck = 0;
const unsigned long FINGER_CHECK_INTERVAL = 500;
int   lastFingerID   = -1;
unsigned long lastFingerTime = 0;
const unsigned long FINGER_DEBOUNCE = 3000;

// ===== Maquina de estados =====
enum EstadoSistema {
  ESTADO_IDLE,
  ESTADO_ESPERANDO_HUELLA_REGISTRO,
  ESTADO_REGISTRO_SEGUNDA_HUELLA,
  ESTADO_MARCANDO
};

EstadoSistema estadoActual       = ESTADO_IDLE;
int    slotRegistrando           = -1;
String nombreRegistrando         = "";
String rutRegistrando            = "";
String emailRegistrando          = "";
unsigned long tiempoUltimoEstado = 0;
const unsigned long TIMEOUT_REGISTRO = 30000;

// ===== Buffer de logs =====
String logBuffer = "";

// ============================================================
// PROTOTIPOS
// ============================================================
JsonArray loadArray(const char* path, DynamicJsonDocument& doc);
void      saveArray(const char* path, DynamicJsonDocument& doc);
String    verificarRostroEnBackend(String personaId);
bool      registrarRostroEnBackend(String personaId);
void      completarRegistroPersona();
void      sincronizarAsistencias();

// ============================================================
// UTILIDADES
// ============================================================

void addLog(String msg) {
  Serial.println(msg);
  logBuffer += msg + "<br>";
  if (logBuffer.length() > 3000) {
    logBuffer = logBuffer.substring(logBuffer.length() - 3000);
  }
}

unsigned long getTimestamp() {
  if (bootEpoch > 0) return bootEpoch + millis() / 1000;
  return millis() / 1000;
}

// ============================================================
// CAMARA
// ============================================================

void initCamera() {
  camera_config_t config;
  config.ledc_channel  = LEDC_CHANNEL_0;
  config.ledc_timer    = LEDC_TIMER_0;
  config.pin_d0        = 5;
  config.pin_d1        = 18;
  config.pin_d2        = 19;
  config.pin_d3        = 21;
  config.pin_d4        = 36;
  config.pin_d5        = 39;
  config.pin_d6        = 34;
  config.pin_d7        = 35;
  config.pin_xclk      = 0;
  config.pin_pclk      = 22;
  config.pin_vsync     = 25;
  config.pin_href      = 23;
  config.pin_sscb_sda  = 26;
  config.pin_sscb_scl  = 27;
  config.pin_pwdn      = 32;
  config.pin_reset     = -1;
  config.xclk_freq_hz  = 20000000;
  config.pixel_format  = PIXFORMAT_JPEG;
  config.frame_size    = FRAMESIZE_QVGA;
  config.jpeg_quality  = 15;
  config.fb_count      = 1;

  if (esp_camera_init(&config) == ESP_OK) {
    camaraIniciada = true;
    addLog("Camara iniciada correctamente");
  } else {
    addLog("Error iniciando camara - continuando sin camara");
  }
}

// Codifica imagen en base64 sin libreria externa
String capturarImagenBase64() {
  if (!camaraIniciada) return "";

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    addLog("Error capturando imagen");
    return "";
  }

  const char* b64chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

  String encoded = "";
  encoded.reserve((fb->len / 3 + 1) * 4);

  int i = 0;
  unsigned char buf3[3], buf4[4];
  int     len  = fb->len;
  uint8_t* data = fb->buf;

  while (len--) {
    buf3[i++] = *(data++);
    if (i == 3) {
      buf4[0] = (buf3[0] & 0xfc) >> 2;
      buf4[1] = ((buf3[0] & 0x03) << 4) + ((buf3[1] & 0xf0) >> 4);
      buf4[2] = ((buf3[1] & 0x0f) << 2) + ((buf3[2] & 0xc0) >> 6);
      buf4[3] = buf3[2] & 0x3f;
      for (i = 0; i < 4; i++) encoded += b64chars[buf4[i]];
      i = 0;
    }
  }
  if (i) {
    for (int j = i; j < 3; j++) buf3[j] = '\0';
    buf4[0] = (buf3[0] & 0xfc) >> 2;
    buf4[1] = ((buf3[0] & 0x03) << 4) + ((buf3[1] & 0xf0) >> 4);
    buf4[2] = ((buf3[1] & 0x0f) << 2) + ((buf3[2] & 0xc0) >> 6);
    for (int j = 0; j < i + 1; j++) encoded += b64chars[buf4[j]];
    while (i++ < 3) encoded += '=';
  }

  esp_camera_fb_return(fb);
  return encoded;
}

// ============================================================
// WIFI Y BACKEND
// ============================================================

void tryConnectWiFi() {
  if (savedSSID.length() == 0) return;
  addLog("Conectando WiFi: " + savedSSID);
  WiFi.begin(savedSSID.c_str(), savedPASS.c_str());
  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 20) {
    delay(500);
    intentos++;
  }
  isOnline = (WiFi.status() == WL_CONNECTED);
  if (isOnline) {
    addLog("WiFi conectado: " + WiFi.localIP().toString());
  } else {
    addLog("WiFi no disponible - modo offline");
  }
}

// Verifica que el rostro coincide con la persona identificada por huella
// Retorna: "rostro_ok", "rostro_no_reconocido", "backend_error",
//          "camara_error" u "offline"
String verificarRostroEnBackend(String personaId) {
  if (!camaraIniciada) return "camara_error";

  if (!isOnline || WiFi.status() != WL_CONNECTED) {
    addLog("Sin WiFi - validacion facial omitida (modo offline)");
    return "offline";
  }

  addLog("Capturando imagen para verificacion...");
  String imgBase64 = capturarImagenBase64();
  if (imgBase64.length() == 0) return "camara_error";

  String payload = "{\"persona_id\":\"" + personaId +
                   "\",\"imagen\":\"" + imgBase64 + "\"}";

  HTTPClient http;
  http.begin(backendURL + "/api/facial/verificar");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(8000);

  int httpCode = http.POST(payload);
  http.end();

  if (httpCode == 200) {
    addLog("Rostro verificado OK");
    return "rostro_ok";
  } else if (httpCode == 404) {
    addLog("Rostro no reconocido");
    return "rostro_no_reconocido";
  } else {
    addLog("Error backend verificacion: " + String(httpCode));
    return "backend_error";
  }
}

// Registra el rostro de una persona nueva en el backend
bool registrarRostroEnBackend(String personaId) {
  if (!camaraIniciada) {
    addLog("Camara no disponible para registro facial");
    return false;
  }
  if (!isOnline || WiFi.status() != WL_CONNECTED) {
    addLog("Sin WiFi - rostro se registrara cuando haya conexion");
    return false;
  }

  addLog("Capturando rostro para registro...");
  String imgBase64 = capturarImagenBase64();
  if (imgBase64.length() == 0) return false;

  String payload = "{\"persona_id\":\"" + personaId +
                   "\",\"imagen\":\"" + imgBase64 + "\"}";

  HTTPClient http;
  http.begin(backendURL + "/api/facial/registrar");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);

  int httpCode = http.POST(payload);
  http.end();

  if (httpCode == 200) {
    addLog("Rostro registrado en backend correctamente");
    return true;
  } else {
    addLog("Error registrando rostro: " + String(httpCode));
    return false;
  }
}

// Sincroniza asistencias pendientes al backend
void sincronizarAsistencias() {
  if (!isOnline) return;

  DynamicJsonDocument doc(2048);
  JsonArray asist = loadArray("/asistencias.json", doc);

  bool hayPendientes = false;
  for (JsonObject a : asist) {
    if (a["sincronizado"] == false) { hayPendientes = true; break; }
  }
  if (!hayPendientes) return;

  addLog("Sincronizando asistencias pendientes...");

  DynamicJsonDocument payload(2048);
  JsonArray registros = payload.createNestedArray("registros");

  for (JsonObject a : asist) {
    if (a["sincronizado"] == false) {
      JsonObject r = registros.createNestedObject();
      r["persona_id"] = a["persona_id"];
      r["nombre"]     = a["nombre"];
      r["tipo"]       = a["tipo"];
      r["metodo"]     = a["metodo"];
    }
  }

  String body;
  serializeJson(payload, body);

  HTTPClient http;
  http.begin(backendURL + "/api/asistencias/sync");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);
  int code = http.POST(body);
  http.end();

  if (code == 200) {
    for (JsonObject a : asist) a["sincronizado"] = true;
    saveArray("/asistencias.json", doc);
    addLog("Sincronizacion completada");
  } else {
    addLog("Error sincronizando: " + String(code));
  }
}

// ============================================================
// SPIFFS — JSON
// ============================================================

JsonArray loadArray(const char* path, DynamicJsonDocument& doc) {
  if (!SPIFFS.exists(path)) {
    doc.set(JsonArray());
    return doc.as<JsonArray>();
  }
  File file = SPIFFS.open(path, "r");
  if (!file) {
    doc.set(JsonArray());
    return doc.as<JsonArray>();
  }
  DeserializationError err = deserializeJson(doc, file);
  file.close();
  if (err || !doc.is<JsonArray>()) doc.set(JsonArray());
  return doc.as<JsonArray>();
}

void saveArray(const char* path, DynamicJsonDocument& doc) {
  File file = SPIFFS.open(path, "w");
  serializeJson(doc, file);
  file.close();
}

void initSPIFFS() {
  if (!SPIFFS.begin(true)) {
    addLog("Error montando SPIFFS");
    return;
  }
  const char* files[] = {
    "/personas.json", "/turnos.json",
    "/asignaciones.json", "/asistencias.json", "/wifi.json"
  };
  for (auto f : files) {
    if (!SPIFFS.exists(f)) {
      File file = SPIFFS.open(f, "w");
      file.println(String(f) == "/wifi.json"
        ? "{\"ssid\":\"\",\"pass\":\"\"}"
        : "[]");
      file.close();
      Serial.printf("Creado %s\n", f);
    }
  }
  addLog("SPIFFS inicializado");
}

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

// ============================================================
// SENSOR DE HUELLAS
// ============================================================

int encontrarSlotLibre() {
  for (int id = 1; id < 127; id++) {
    if (finger.loadModel(id) != FINGERPRINT_OK) return id;
  }
  return -1;
}

bool turnoActivo(const String& personaId) {
  DynamicJsonDocument doc(1024);
  JsonArray asign = loadArray("/asignaciones.json", doc);
  for (JsonObject a : asign) {
    if (a["persona_id"] == personaId) return true;
  }
  return false;
}

// Guarda la persona en PostgreSQL, en JSON local y registra su rostro
void completarRegistroPersona() {
  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);

  // 1. Por defecto usamos ID local (por si estamos offline)
  String idReal = String(personas.size() + 1); 

  // 2. Si hay internet, creamos la persona en el Backend PRIMERO
  if (isOnline) {
    addLog("Guardando usuario en base de datos (PostgreSQL)...");
    HTTPClient http;
    http.begin(backendURL + "/api/personas");
    http.addHeader("Content-Type", "application/json");

    String payload = "{\"nombre\":\"" + nombreRegistrando + 
                     "\",\"rut\":\"" + rutRegistrando + 
                     "\",\"email\":\"" + emailRegistrando + 
                     "\",\"huella_id\":" + String(slotRegistrando) + "}";

    int httpCode = http.POST(payload);
    if (httpCode == 200) {
      String response = http.getString();
      DynamicJsonDocument respDoc(256);
      deserializeJson(respDoc, response);
      if (respDoc.containsKey("id")) {
        idReal = respDoc["id"].as<String>(); // Capturamos el ID real de Neon
        addLog("Persona creada en BD con ID: " + idReal);
      }
    } else {
      addLog("Error creando persona en backend: " + String(httpCode));
    }
    http.end();
  }

  // 3. Guardar en JSON local con el ID real
  JsonObject p = personas.createNestedObject();
  p["id"]             = idReal;
  p["nombre"]         = nombreRegistrando;
  p["rut"]            = rutRegistrando;
  p["email"]          = emailRegistrando;
  p["huella_id"]      = slotRegistrando;
  p["fecha_registro"] = getTimestamp();
  p["sincronizado"]   = isOnline;

  saveArray("/personas.json", doc);

  // 4. Registrar rostro apuntando al ID de la Base de Datos
  if (camaraIniciada && isOnline) {
    addLog("=== MIRE A LA CAMARA DEL ESP32 AHORA ===");
    delay(2500); // Dar 2.5 segundos para que la persona pose
    registrarRostroEnBackend(idReal);
  } else {
    addLog("Rostro pendiente (Sin WiFi o sin camara)");
  }

  // Limpiar variables de registro
  slotRegistrando   = -1;
  nombreRegistrando = "";
  rutRegistrando    = "";
  emailRegistrando  = "";
}

// Registra asistencia con verificacion facial si hay backend disponible
String registrarAsistenciaAutomatica(int huellaID) {
  DynamicJsonDocument docP(2048);
  JsonArray personas = loadArray("/personas.json", docP);

  String personaId = "";
  String nombre    = "";

  for (JsonObject p : personas) {
    if (p["huella_id"] == huellaID) {
      personaId = p["id"].as<String>();
      nombre    = p["nombre"].as<String>();
      break;
    }
  }

  if (personaId == "") return "Huella no asociada a usuario";
  if (!turnoActivo(personaId)) return "Sin turno asignado: " + nombre;

  // Verificacion facial
  addLog("Huella OK - verificando rostro...");
  String resultadoFacial = verificarRostroEnBackend(personaId);

  String metodo = "huella";

  if (resultadoFacial == "rostro_ok") {
    metodo = "facial+huella";
    addLog("Verificacion biometrica completa");
  } else if (resultadoFacial == "rostro_no_reconocido") {
    return "Verificacion facial fallida para: " + nombre;
  } else {
    // offline, camara_error o backend_error: degradacion graciosa
    addLog("Solo huella (facial no disponible)");
  }

  // Determinar tipo entrada/salida
  DynamicJsonDocument docA(2048);
  JsonArray asist = loadArray("/asistencias.json", docA);

  String tipo = "entrada";
  for (int i = asist.size() - 1; i >= 0; i--) {
    JsonObject a = asist[i];
    if (a["persona_id"] == personaId) {
      tipo = (String(a["tipo"].as<const char*>()) == "entrada")
             ? "salida" : "entrada";
      break;
    }
  }

  JsonObject a = asist.createNestedObject();
  a["persona_id"]   = personaId;
  a["nombre"]       = nombre;
  a["tipo"]         = tipo;
  a["metodo"]       = metodo;
  a["timestamp"]    = getTimestamp();
  a["sincronizado"] = false;

  saveArray("/asistencias.json", docA);

  String tipoMayus = tipo;
  tipoMayus.toUpperCase();
  return tipoMayus + " registrada\nUsuario: " + nombre +
         "\nMetodo: " + metodo;
}

// ============================================================
// HANDLERS WEB
// ============================================================

void servirArchivo(const char* path, const char* tipo) {
  if (!SPIFFS.exists(path)) {
    server.send(404, "text/plain",
      "Archivo no encontrado: " + String(path));
    return;
  }
  File f = SPIFFS.open(path, "r");
  server.streamFile(f, tipo);
  f.close();
}

void handleWiFiConfig() {
  if (server.hasArg("ssid") && server.hasArg("pass")) {
    saveWiFiConfig(server.arg("ssid"), server.arg("pass"));
    server.send(200, "text/plain", "Configuracion guardada. Reiniciando...");
    delay(1000);
    ESP.restart();
  } else {
    server.send(400, "text/plain", "Faltan parametros");
  }
}

void handleRegisterUser() {
  if (!server.hasArg("name") || !server.hasArg("rut") ||
      !server.hasArg("email")) {
    server.send(400, "text/plain", "Faltan datos requeridos");
    return;
  }

  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);
  String rut = server.arg("rut");

  for (JsonObject p : personas) {
    if (p["rut"] == rut) {
      server.send(400, "text/plain", "RUT ya registrado");
      return;
    }
  }

  int slot = encontrarSlotLibre();
  if (slot < 0) {
    server.send(500, "text/plain", "No hay slots libres en el sensor");
    return;
  }

  slotRegistrando    = slot;
  nombreRegistrando  = server.arg("name");
  rutRegistrando     = rut;
  emailRegistrando   = server.arg("email");
  estadoActual       = ESTADO_ESPERANDO_HUELLA_REGISTRO;
  tiempoUltimoEstado = millis();

  server.send(200, "text/plain", "Coloque el dedo en el sensor...");
}

void handleCreateTurn() {
  if (!server.hasArg("nombre") || !server.hasArg("inicio") ||
      !server.hasArg("fin")    || !server.hasArg("dias")) {
    server.send(400, "text/plain", "Datos incompletos");
    return;
  }
  DynamicJsonDocument doc(1024);
  JsonArray turnos = loadArray("/turnos.json", doc);
  JsonObject t = turnos.createNestedObject();
  t["id"]     = String(turnos.size() + 1);
  t["nombre"] = server.arg("nombre");
  t["inicio"] = server.arg("inicio");
  t["fin"]    = server.arg("fin");
  t["dias"]   = server.arg("dias");
  saveArray("/turnos.json", doc);
  server.send(200, "text/plain", "Turno creado");
}

void handleAssignTurn() {
  if (!server.hasArg("persona") || !server.hasArg("turno")) {
    server.send(400, "text/plain", "Falta persona o turno");
    return;
  }
  DynamicJsonDocument doc(1024);
  JsonArray asignaciones = loadArray("/asignaciones.json", doc);
  String personaId = server.arg("persona");
  String turnoId   = server.arg("turno");

  for (JsonObject a : asignaciones) {
    if (a["persona_id"] == personaId) {
      server.send(400, "text/plain", "Persona ya tiene turno asignado");
      return;
    }
  }
  JsonObject a = asignaciones.createNestedObject();
  a["persona_id"]       = personaId;
  a["turno_id"]         = turnoId;
  a["fecha_asignacion"] = getTimestamp();
  saveArray("/asignaciones.json", doc);
  server.send(200, "text/plain", "Turno asignado");
}

void handleMarcarAsistencia() {
  addLog("Esperando huella...");
  int p = finger.getImage();
  if (p != FINGERPRINT_OK) {
    server.send(500, "text/plain", "No se detecta huella");
    return;
  }
  if (finger.image2Tz() != FINGERPRINT_OK) {
    server.send(500, "text/plain", "Error procesando imagen");
    return;
  }
  if (finger.fingerSearch() != FINGERPRINT_OK) {
    server.send(500, "text/plain", "Huella no encontrada");
    return;
  }
  if (finger.fingerID < 1) {
    server.send(500, "text/plain", "Huella no encontrada");
    return;
  }
  String resultado = registrarAsistenciaAutomatica(finger.fingerID);
  server.send(200, "text/plain", resultado);
}

// APIs REST — streamFile para no cargar en RAM
void handleGetPersonas() {
  File f = SPIFFS.open("/personas.json", "r");
  server.streamFile(f, "application/json");
  f.close();
}

void handleGetTurnos() {
  File f = SPIFFS.open("/turnos.json", "r");
  server.streamFile(f, "application/json");
  f.close();
}

void handleGetAsignaciones() {
  File f = SPIFFS.open("/asignaciones.json", "r");
  server.streamFile(f, "application/json");
  f.close();
}

void handleGetAsistencias() {
  File f = SPIFFS.open("/asistencias.json", "r");
  server.streamFile(f, "application/json");
  f.close();
}

void handleLimpiarDatos() {
  if (!server.hasArg("codigo") || server.arg("codigo") != "1234") {
    server.send(403, "text/plain", "Codigo incorrecto");
    return;
  }
  const char* files[] = {
    "/personas.json", "/turnos.json",
    "/asignaciones.json", "/asistencias.json"
  };
  for (auto f : files) {
    File file = SPIFFS.open(f, "w");
    file.println("[]");
    file.close();
  }
  for (int id = 1; id < 127; id++) finger.deleteModel(id);
  addLog("Sistema limpiado");
  server.send(200, "text/plain",
    "Sistema limpiado correctamente\n\n"
    "Se eliminaron:\n- Todas las personas\n- Todos los turnos\n"
    "- Todas las asignaciones\n- Todas las asistencias\n"
    "- Todas las huellas del sensor");
}

void handleSincronizar() {
  if (!isOnline) {
    server.send(503, "text/plain", "Sin conexion WiFi");
    return;
  }
  sincronizarAsistencias();
  server.send(200, "text/plain", "Sincronizacion ejecutada");
}

void handleSetBackend() {
  if (!server.hasArg("url")) {
    server.send(400, "text/plain", "Falta url");
    return;
  }
  backendURL = server.arg("url");
  addLog("Backend actualizado: " + backendURL);
  server.send(200, "text/plain", "Backend: " + backendURL);
}

// ============================================================
// SETUP
// ============================================================

void setup() {
  pinMode(13, INPUT_PULLUP); // Configuramos el pin 13 con resistencia interna
  
  // Si al arrancar el pin 13 esta unido a GND (puente físico)
  if (digitalRead(13) == LOW) {
    delay(1000); // Debounce simple
    if (digitalRead(13) == LOW) {
      initSPIFFS(); // Aseguramos que SPIFFS este listo [cite: 116]
      saveWiFiConfig("", ""); // Borramos el WiFi 
      Serial.println("¡RESET DE WIFI DETECTADO POR HARDWARE!");
      // Opcional: parpadear el LED del flash para avisar
    }
  }
  
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\nESP32 Sistema de Asistencia");
  Serial.println("============================");

  // 1. Camara primero
  initCamera();
  delay(500);

  // 2. Sensor de huellas
  FingerSerial.begin(57600, SERIAL_8N1, 14, 15);
  finger.begin(57600);
  if (finger.verifyPassword()) {
    addLog("Sensor AS608 conectado");
  } else {
    addLog("Sensor AS608 NO detectado - verificar GPIO14/15");
  }

  // 3. SPIFFS
  initSPIFFS();
  delay(500);
  loadWiFiConfig();

  // 4. WiFi externo
  tryConnectWiFi();

  // 5. AP siempre activo para acceso local
  WiFi.mode(isOnline ? WIFI_AP_STA : WIFI_AP);
  WiFi.setTxPower(WIFI_POWER_11dBm);
  WiFi.softAP(apSSID, apPASS, 1, 0, 4);
  WiFi.softAPConfig(
    IPAddress(192, 168, 4, 1),
    IPAddress(192, 168, 4, 1),
    IPAddress(255, 255, 255, 0)
  );

  addLog("AP: " + String(apSSID) +
         " | IP: " + WiFi.softAPIP().toString());
  if (isOnline) addLog("WiFi: " + WiFi.localIP().toString());

  // 6. Paginas HTML desde SPIFFS
  server.on("/",             []() { servirArchivo("/index.html",       "text/html"); });
  server.on("/register",     []() { servirArchivo("/register.html",    "text/html"); });
  server.on("/gestion",      []() { servirArchivo("/gestion.html",     "text/html"); });
  server.on("/personas",     []() { servirArchivo("/personas.html",    "text/html"); });
  server.on("/asistencias",  []() { servirArchivo("/asistencias.html", "text/html"); });
  server.on("/turnos",       []() { servirArchivo("/turnos.html",      "text/html"); });
  server.on("/asignaciones", []() { servirArchivo("/asignaciones.html","text/html"); });
  server.on("/wifi-setup",   []() { servirArchivo("/wifi-setup.html",  "text/html"); });

  // 7. Rutas de accion
  server.on("/wifi-config",    handleWiFiConfig);
  server.on("/registrar",      handleRegisterUser);
  server.on("/crear_turno",    handleCreateTurn);
  server.on("/asignar",        handleAssignTurn);
  server.on("/marcar",         handleMarcarAsistencia);
  server.on("/limpiar",        handleLimpiarDatos);
  server.on("/sincronizar",    handleSincronizar);
  server.on("/set-backend",    handleSetBackend);

  // 8. APIs REST
  server.on("/api/personas",     handleGetPersonas);
  server.on("/api/turnos",       handleGetTurnos);
  server.on("/api/asignaciones", handleGetAsignaciones);
  server.on("/api/asistencias",  handleGetAsistencias);

  // 9. Estado del sistema en JSON
  server.on("/estado", []() {
    String json = "{";
    json += "\"estado\":\""  + String(estadoActual == ESTADO_IDLE ? "idle" : "ocupado") + "\",";
    json += "\"online\":"    + String(isOnline ? "true" : "false") + ",";
    json += "\"camara\":"    + String(camaraIniciada ? "true" : "false") + ",";
    json += "\"backend\":\"" + backendURL + "\"";
    json += "}";
    server.send(200, "application/json", json);
  });

  // 10. Logs en navegador
  server.on("/logs", []() {
    String html = "<!DOCTYPE html><html><head>";
    html += "<meta charset='utf-8'>";
    html += "<meta http-equiv='refresh' content='2'>";
    html += "<title>Logs ESP32</title></head><body>";
    html += "<h3>Log del sistema</h3>";
    html += "<div style='font-family:monospace;font-size:12px'>";
    html += logBuffer;
    html += "</div></body></html>";
    server.send(200, "text/html", html);
  });

  server.begin();
  addLog("Sistema listo - acceda a http://192.168.4.1");
}

// ============================================================
// LOOP
// ============================================================

void loop() {
  server.handleClient();

  unsigned long ahora = millis();

  // Timeout de estados bloqueados
  if (estadoActual != ESTADO_IDLE &&
      (ahora - tiempoUltimoEstado) > TIMEOUT_REGISTRO) {
    addLog("Timeout registro - volviendo a IDLE");
    estadoActual = ESTADO_IDLE;
  }

  // ===== Registro: primera huella =====
  if (estadoActual == ESTADO_ESPERANDO_HUELLA_REGISTRO) {
    int p = finger.getImage();
    if (p == FINGERPRINT_OK) {
      p = finger.image2Tz(1);
      if (p == FINGERPRINT_OK) {
        addLog("Primera huella OK - retire el dedo...");
        estadoActual       = ESTADO_REGISTRO_SEGUNDA_HUELLA;
        tiempoUltimoEstado = millis();
      }
    }
    return;
  }

  // ===== Registro: segunda huella =====
  if (estadoActual == ESTADO_REGISTRO_SEGUNDA_HUELLA) {
    int p = finger.getImage();
    if (p == FINGERPRINT_NOFINGER) return;
    if (p == FINGERPRINT_OK) {
      p = finger.image2Tz(2);
      if (p == FINGERPRINT_OK) {
        p = finger.createModel();
        if (p == FINGERPRINT_OK) {
          p = finger.storeModel(slotRegistrando);
          if (p == FINGERPRINT_OK) {
            completarRegistroPersona();
            addLog("Registro completado exitosamente");
          } else {
            addLog("Error guardando huella en sensor");
          }
        } else {
          addLog("Huellas no coinciden - intente nuevamente");
          estadoActual       = ESTADO_ESPERANDO_HUELLA_REGISTRO;
          tiempoUltimoEstado = millis();
          return;
        }
      }
      estadoActual = ESTADO_IDLE;
    }
    return;
  }

  // ===== IDLE: escaneo automatico cada 500ms =====
  if (estadoActual == ESTADO_IDLE &&
      (ahora - lastFingerCheck) >= FINGER_CHECK_INTERVAL) {
    lastFingerCheck = ahora;

    int p = finger.getImage();
    if (p == FINGERPRINT_OK) {
      p = finger.image2Tz();
      if (p == FINGERPRINT_OK) {
        p = finger.fingerSearch();
        if (p == FINGERPRINT_OK && finger.fingerID > 0) {
          int huellaID = finger.fingerID;
          if (huellaID != lastFingerID ||
              (ahora - lastFingerTime) > FINGER_DEBOUNCE) {
            lastFingerID   = huellaID;
            lastFingerTime = ahora;
            addLog("Huella detectada ID: " + String(huellaID));
            String resultado = registrarAsistenciaAutomatica(huellaID);
            addLog(resultado);
          }
        }
      }
    }
  }

  // Sincronizacion automatica cada 5 minutos si hay conexion
  static unsigned long lastSync = 0;
  if (isOnline && (ahora - lastSync) > 300000UL) {
    lastSync = ahora;
    sincronizarAsistencias();
  }
}
