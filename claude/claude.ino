// ============================================================
// ESP32-CAM Sistema de Asistencia - VERSIÓN DEFINITIVA
// Centinela (Facial) + Huella + Fetch Backend + Gestión Web
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
#include "mqtt_client.h"
#include "esp_crt_bundle.h" 

esp_mqtt_client_handle_t mqtt_client = NULL;
bool mqttConnected = false;

// ===== Sensor de huellas (RX=GPIO14, TX=GPIO15) =====
HardwareSerial FingerSerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&FingerSerial);

WebServer server(80);

// ===== Configuracion AP =====
const char* apSSID   = "ESP32-ASISTENCIA";
const char* apPASS   = "12345678";

// ===== WiFi externo configurable =====
String savedSSID = "";
String savedPASS = "";
bool   isOnline  = false;

// ===== Backend y MQTT =====
String backendURL     = "https://sculpture-kong-filtering-essential.trycloudflare.com";
String mqttBroker     = ""; 
String lastCapturedImageUrl = "";
bool   camaraIniciada = false;

// ===== Timestamp y Control de Tiempos =====
unsigned long bootEpoch = 0;
unsigned long cooldownAsistencia = 0;             
const unsigned long COOLDOWN_TIEMPO = 8000;       

// ===== Escaneo automatico =====
unsigned long lastFingerCheck = 0;
const unsigned long FINGER_CHECK_INTERVAL = 1000; 
unsigned long lastFaceCheck = 0;
const unsigned long FACE_CHECK_INTERVAL = 6000;   
int   lastFingerID   = -1;
unsigned long lastFingerTime = 0;
const unsigned long FINGER_DEBOUNCE = 4000;       

// ===== Maquina de estados =====
enum EstadoSistema {
  ESTADO_IDLE = 0,
  ESTADO_ESPERANDO_HUELLA_REGISTRO = 1,
  ESTADO_ESPERANDO_SOLTAR_DEDO = 4, 
  ESTADO_REGISTRO_SEGUNDA_HUELLA = 2,
  ESTADO_REGISTRO_FACIAL = 3,
  ESTADO_PROCESANDO_ASISTENCIA = 5
};

EstadoSistema estadoActual    = ESTADO_IDLE;
int    slotRegistrando        = -1;
String nombreRegistrando      = "";
String rutRegistrando         = "";
String emailRegistrando       = "";
unsigned long tiempoUltimoEstado = 0;
const unsigned long TIMEOUT_REGISTRO = 30000;

int intentosFacial = 0;
String idParaRostro = "";
String logBuffer = "";

// ============================================================
// PROTOTIPOS (Vitales para evitar errores del compilador)
// ============================================================
JsonArray loadArray(const char* path, DynamicJsonDocument& doc);
void saveArray(const char* path, DynamicJsonDocument& doc);
String identificarPorRostro();
bool registrarRostroEnBackend(String personaId);
void completarRegistroPersona();
void sincronizarAsistencias();
void sincronizarPersonasDesdeBackend();
String procesarAsistencia(String personaId, String metodo);
String buscarPersonaPorHuella(int huellaID);
void addLog(String msg);
unsigned long getTimestamp();

void handleWiFiConfig();
void handleRegisterUser();
void handleCreateTurn();
void handleAssignTurn();
void handleMarcarAsistencia();
void handleLimpiarDatos();
void handleSincronizar();
void handleFetchPersonas();
void handleSetBackend();
void handleBorrarPersona();
void handleBorrarTurno();
void handleBorrarAsignacion();
void handleGetPersonas();
void handleGetTurnos();
void handleGetAsignaciones();
void handleGetAsistencias();
void handleUltimoRegistro();
void servirArchivo(const char* path, const char* tipo);

// ============================================================
// EVENTOS MQTT Y LOGS
// ============================================================
static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data) {
  esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
  switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
      addLog("MQTT Conectado por WebSockets");
      mqttConnected = true;
      esp_mqtt_client_subscribe(mqtt_client, "esp32/respuesta/facial", 0);
      break;
    case MQTT_EVENT_DISCONNECTED:
      mqttConnected = false;
      break;
    case MQTT_EVENT_DATA: {
      String topic = String(event->topic).substring(0, event->topic_len);
      String mensaje = String(event->data).substring(0, event->data_len);
      if (topic == "esp32/respuesta/facial") {
        DynamicJsonDocument doc(512);
        deserializeJson(doc, mensaje);
        if (doc["status"] == "ok") {
          addLog("Rostro guardado OK en Backend");
          String fileName = doc["file_name"].as<String>();
          String urlBase = backendURL;
          if (urlBase.endsWith("/")) urlBase = urlBase.substring(0, urlBase.length() - 1);
          lastCapturedImageUrl = urlBase + "/static/previews/" + fileName;
          estadoActual = ESTADO_IDLE;
        } else {
          addLog("Rostro rechazado: " + doc["mensaje"].as<String>());
        }
      }
      break;
    }
    default:
      break;
  }
}

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
    addLog("Camara iniciada");
  } else {
    addLog("Error iniciando camara");
  }
  
  sensor_t * s = esp_camera_sensor_get();
  s->set_brightness(s, 1);     
  s->set_contrast(s, 1);
  s->set_special_effect(s, 0);
  s->set_vflip(s, 1);          
}

String capturarImagenBase64() {
  if (!camaraIniciada) return "";
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return "";

  const char* b64chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  String encoded = "";
  encoded.reserve((fb->len / 3 + 1) * 4);

  int i = 0;
  unsigned char buf3[3], buf4[4];
  int len  = fb->len;
  uint8_t* data = fb->buf;
  int contador_wdt = 0;

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
    contador_wdt++;
    if (contador_wdt % 500 == 0) yield();
  }
  esp_camera_fb_return(fb);
  return encoded;
}

// ============================================================
// WIFI Y MANTENIMIENTO MQTT
// ============================================================
void tryConnectWiFi() {
  if (savedSSID.length() == 0) {
    isOnline = false;
    return;
  }
  addLog("Conectando WiFi: " + savedSSID);
  WiFi.mode(WIFI_STA); 
  WiFi.setSleep(false);
  
  IPAddress dns(8, 8, 8, 8);
  WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE, dns);
  
  WiFi.begin(savedSSID.c_str(), savedPASS.c_str());
  
  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 20) {
    delay(500);
    Serial.print(".");
    intentos++;
  }
  Serial.println();
  isOnline = (WiFi.status() == WL_CONNECTED);
  
  if (isOnline) addLog("WiFi conectado");
  else { addLog("WiFi no disponible"); WiFi.disconnect(); }
}

void mantenerConexionMQTT() {
  if (mqttBroker == "" || !isOnline) return;
  if (mqtt_client != NULL) return;
  
  String brokerUrl = mqttBroker;
  if (brokerUrl.startsWith("https://")) brokerUrl = brokerUrl.substring(8);
  else if (brokerUrl.startsWith("http://")) brokerUrl = brokerUrl.substring(7);
  if (brokerUrl.startsWith("wss://")) brokerUrl = brokerUrl.substring(6);
  else if (brokerUrl.startsWith("ws://")) brokerUrl = brokerUrl.substring(5);
  
  if (!brokerUrl.endsWith("/mqtt")) brokerUrl += brokerUrl.endsWith("/") ? "mqtt" : "/mqtt";

  brokerUrl = "wss://" + brokerUrl;
  esp_mqtt_client_config_t mqtt_cfg = {};
  
  #if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
    mqtt_cfg.broker.address.uri = brokerUrl.c_str();
    mqtt_cfg.broker.verification.crt_bundle_attach = esp_crt_bundle_attach; 
  #else
    mqtt_cfg.uri = brokerUrl.c_str();
    mqtt_cfg.crt_bundle_attach = esp_crt_bundle_attach; 
  #endif

  mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
  esp_mqtt_client_register_event(mqtt_client, (esp_mqtt_event_id_t)ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
  esp_mqtt_client_start(mqtt_client);
}

void sincronizarPersonasDesdeBackend() {
  if (!isOnline || WiFi.status() != WL_CONNECTED) {
    addLog("Sin WiFi: No se puede fetchear personas.");
    return;
  }
  addLog("Fetcheando lista de personas desde Backend...");
  HTTPClient http;
  http.begin(backendURL + "/api/personas"); 
  http.setTimeout(10000);

  int httpCode = http.GET();
  if (httpCode == 200) {
    DynamicJsonDocument doc(8192); 
    DeserializationError error = deserializeJson(doc, http.getStream());

    if (!error) {
      File file = SPIFFS.open("/personas.json", "w");
      serializeJson(doc, file);
      file.close();
      addLog("Personas fetcheadas y guardadas. Total: " + String(doc.size()));
    } else {
      addLog("Error parseando JSON de personas.");
    }
  } else {
    addLog("Error HTTP al fetchear personas: " + String(httpCode));
  }
  http.end();
  yield();
}

// ============================================================
// LÓGICA DE ASISTENCIA BIOMÉTRICA
// ============================================================
String identificarPorRostro() {
  if (!camaraIniciada || !isOnline || WiFi.status() != WL_CONNECTED) return "";
  
  String imgBase64 = capturarImagenBase64();
  if (imgBase64.length() == 0) return "";
  
  String payload = "{\"imagen\":\"" + imgBase64 + "\"}";
  HTTPClient http;
  http.begin(backendURL + "/api/facial/identificar");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(8000); 

  int httpCode = http.POST(payload);
  String personaIdEncontrada = "";
  
  if (httpCode == 200) {
    DynamicJsonDocument doc(256);
    deserializeJson(doc, http.getString());
    if (doc.containsKey("persona_id")) {
      personaIdEncontrada = doc["persona_id"].as<String>();
    }
  }
  http.end();
  return personaIdEncontrada;
}

String buscarPersonaPorHuella(int huellaID) {
  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);
  for (JsonObject p : personas) {
    if (p["huella_id"].as<int>() == huellaID) {
      return p["id"].as<String>();
    }
  }
  return "";
}

bool turnoActivo(const String& personaId) {
  DynamicJsonDocument doc(1024);
  JsonArray asign = loadArray("/asignaciones.json", doc);
  for (JsonObject a : asign) {
    if (a["persona_id"] == personaId) return true;
  }
  return false;
}

String procesarAsistencia(String personaId, String metodo) {
  DynamicJsonDocument docP(2048);
  JsonArray personas = loadArray("/personas.json", docP);
  String nombre = "";
  
  for (JsonObject p : personas) {
    if (p["id"].as<String>() == personaId) {
      nombre = p["nombre"].as<String>();
      break;
    }
  }

  if (nombre == "") return "Persona ID no existe localmente";
  if (!turnoActivo(personaId)) return "Sin turno asignado: " + nombre;

  DynamicJsonDocument docA(2048);
  JsonArray asist = loadArray("/asistencias.json", docA);
  
  String tipo = "entrada";
  for (int i = asist.size() - 1; i >= 0; i--) {
    JsonObject a = asist[i];
    if (a["persona_id"] == personaId) {
      tipo = (String(a["tipo"].as<const char*>()) == "entrada") ? "salida" : "entrada";
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
  return tipoMayus + " OK: " + nombre + " (" + metodo + ")";
}

// ============================================================
// REGISTRO DE USUARIOS
// ============================================================
int encontrarSlotLibre() {
  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);
  int maxId = 0;
  for (JsonObject p : personas) {
    int hId = p["huella_id"].as<int>();
    if (hId > maxId) maxId = hId;
  }
  int siguienteLibre = maxId + 1;
  if (siguienteLibre > 127) return -1; 
  return siguienteLibre;
}

void completarRegistroPersona() {
  if (!isOnline) {
    addLog("Error: Sin conexión. Abortando registro.");
    estadoActual = ESTADO_IDLE;
    nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = ""; slotRegistrando = -1;
    return;
  }

  HTTPClient http;
  http.begin(backendURL + "/api/personas");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);
  
  String payload = "{\"nombre\":\"" + nombreRegistrando + 
                   "\",\"rut\":\"" + rutRegistrando + 
                   "\",\"email\":\"" + emailRegistrando + 
                   "\",\"huella_id\":" + String(slotRegistrando) + "}";
                   
  int httpCode = http.POST(payload);
  String idReal = "";

  if (httpCode == 200 || httpCode == 201) {
    String response = http.getString();
    DynamicJsonDocument respDoc(256);
    deserializeJson(respDoc, response);
    if (respDoc.containsKey("id")) {
        idReal = respDoc["id"].as<String>();
        addLog("Usuario creado en BD ID: " + idReal);
    }
  } else {
    addLog("Error BD (Cod:" + String(httpCode) + "). Abortando.");
    estadoActual = ESTADO_IDLE;
    if(slotRegistrando > 0) finger.deleteModel(slotRegistrando);
    nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = ""; slotRegistrando = -1;
    http.end();
    return;
  }
  http.end();

  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);
  JsonObject p = personas.createNestedObject();
  p["id"]             = idReal;
  p["nombre"]         = nombreRegistrando;
  p["rut"]            = rutRegistrando;
  p["email"]          = emailRegistrando;
  p["huella_id"]      = slotRegistrando;
  p["fecha_registro"] = getTimestamp();
  p["sincronizado"]   = true;
  saveArray("/personas.json", doc);
  
  if (camaraIniciada) {
    addLog("Mire a la cámara para la foto...");
    idParaRostro = idReal;   
    intentosFacial = 0;      
    estadoActual = ESTADO_REGISTRO_FACIAL;
    tiempoUltimoEstado = millis();
  } else {
    estadoActual = ESTADO_IDLE;
    nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = ""; slotRegistrando = -1;
  }
}

bool registrarRostroEnBackend(String personaId) {
  if (!camaraIniciada || !isOnline) return false;
  if (mqtt_client == NULL) mantenerConexionMQTT();
  if (!mqttConnected || mqtt_client == NULL) return false;

  String imgBase64 = capturarImagenBase64();
  if (imgBase64.length() == 0) return false;

  esp_mqtt_client_publish(mqtt_client, "esp32/imagen/start", personaId.c_str(), 0, 0, 0);
  
  int chunkSize = 500; 
  int longitudTotal = imgBase64.length();
  for (int i = 0; i < longitudTotal; i += chunkSize) {
    String chunk = imgBase64.substring(i, min(i + chunkSize, longitudTotal));
    esp_mqtt_client_publish(mqtt_client, "esp32/imagen/part", chunk.c_str(), 0, 0, 0);
    delay(60); 
    yield(); 
  }
  esp_mqtt_client_publish(mqtt_client, "esp32/imagen/end", "fin", 0, 0, 0);
  return true; 
}

void sincronizarAsistencias() {
  if (!isOnline) return;
  DynamicJsonDocument doc(2048);
  JsonArray asist = loadArray("/asistencias.json", doc);

  bool hayPendientes = false;
  for (JsonObject a : asist) {
    if (a["sincronizado"] == false) { hayPendientes = true; break; }
  }
  if (!hayPendientes) return;

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
  String body; serializeJson(payload, body);

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
  }
}

// ============================================================
// SPIFFS — JSON
// ============================================================
JsonArray loadArray(const char* path, DynamicJsonDocument& doc) {
  if (!SPIFFS.exists(path)) { doc.set(JsonArray()); return doc.as<JsonArray>(); }
  File file = SPIFFS.open(path, "r");
  if (!file) { doc.set(JsonArray()); return doc.as<JsonArray>(); }
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
  if (!SPIFFS.begin(true)) return;
  const char* files[] = { "/personas.json", "/turnos.json", "/asignaciones.json", "/asistencias.json", "/wifi.json" };
  for (auto f : files) {
    if (!SPIFFS.exists(f)) {
      File file = SPIFFS.open(f, "w");
      file.println(String(f) == "/wifi.json" ? "{\"ssid\":\"\",\"pass\":\"\",\"backend\":\"http://172.20.10.3:5000\",\"mqtt\":\"\"}" : "[]");
      file.close();
    }
  }
}

void loadWiFiConfig() {
  File file = SPIFFS.open("/wifi.json", "r");
  if (file) {
    DynamicJsonDocument doc(512);
    deserializeJson(doc, file);
    if (doc.containsKey("ssid")) savedSSID = doc["ssid"].as<String>();
    if (doc.containsKey("pass")) savedPASS = doc["pass"].as<String>();
    if (doc.containsKey("backend")) backendURL = doc["backend"].as<String>();
    if (doc.containsKey("mqtt")) mqttBroker = doc["mqtt"].as<String>();
    file.close();
  }
}

void saveConfig(String ssid, String pass, String backend, String mqtt) {
  DynamicJsonDocument doc(512);
  doc["ssid"] = ssid; doc["pass"] = pass; doc["backend"] = backend; doc["mqtt"] = mqtt;
  File file = SPIFFS.open("/wifi.json", "w");
  serializeJson(doc, file); file.close();
  savedSSID = ssid; savedPASS = pass; backendURL = backend; mqttBroker = mqtt;
}

void servirArchivo(const char* path, const char* tipo) {
  if (!SPIFFS.exists(path)) { server.send(404, "text/plain", "Archivo no encontrado"); return; }
  File f = SPIFFS.open(path, "r");
  server.streamFile(f, tipo);
  f.close();
  yield(); 
}

// ============================================================
// HANDLERS WEB
// ============================================================
void handleWiFiConfig() {
  if (server.hasArg("ssid") && server.hasArg("pass")) {
    saveConfig(server.arg("ssid"), server.arg("pass"), server.hasArg("backend") ? server.arg("backend") : backendURL, server.hasArg("mqtt") ? server.arg("mqtt") : mqttBroker);
    server.send(200, "text/plain", "Guardado. Reiniciando...");
    delay(1500); ESP.restart();
  } else { server.send(400, "text/plain", "Faltan parametros"); }
}

void handleRegisterUser() {
  if (!server.hasArg("name") || !server.hasArg("rut")) { server.send(400, "text/plain", "Faltan datos"); return; }
  int slot = encontrarSlotLibre();
  if (slot < 0) { server.send(500, "text/plain", "Sin slots"); return; }
  slotRegistrando = slot; nombreRegistrando = server.arg("name"); rutRegistrando = server.arg("rut"); emailRegistrando = server.arg("email");
  estadoActual = ESTADO_ESPERANDO_HUELLA_REGISTRO; tiempoUltimoEstado = millis();
  server.send(200, "text/plain", "OK: Ponga el dedo...");
}

void handleCreateTurn() {
  if (!server.hasArg("nombre") || !server.hasArg("inicio") || !server.hasArg("fin") || !server.hasArg("dias")) {
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
  
  for (JsonObject a : asignaciones) {
    if (a["persona_id"] == personaId) {
      server.send(400, "text/plain", "Persona ya tiene turno asignado");
      return;
    }
  }
  JsonObject a = asignaciones.createNestedObject();
  a["persona_id"]       = personaId;
  a["turno_id"]         = server.arg("turno");
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
  String pId = buscarPersonaPorHuella(finger.fingerID);
  String resultado = procesarAsistencia(pId, "huella_manual");
  server.send(200, "text/plain", resultado);
}

void handleLimpiarDatos() {
  if (!server.hasArg("codigo") || server.arg("codigo") != "1234") {
    server.send(403, "text/plain", "Codigo incorrecto");
    return;
  }
  const char* files[] = {"/personas.json", "/turnos.json", "/asignaciones.json", "/asistencias.json"};
  for (auto f : files) {
    File file = SPIFFS.open(f, "w");
    file.println("[]");
    file.close();
  }
  for (int id = 1; id < 127; id++) finger.deleteModel(id);
  addLog("Sistema limpiado");
  server.send(200, "text/plain", "Sistema limpiado correctamente");
}

void handleSincronizar() {
  if (!isOnline) { server.send(503, "text/plain", "Sin conexion"); return; }
  sincronizarAsistencias();
  server.send(200, "text/plain", "Sincronizacion ejecutada");
}

void handleFetchPersonas() {
  if (!isOnline) { server.send(503, "text/plain", "Sin conexion WiFi"); return; }
  sincronizarPersonasDesdeBackend();
  server.send(200, "text/plain", "Personas obtenidas. Revisa los logs.");
}

void handleSetBackend() {
  if (!server.hasArg("url")) { server.send(400, "text/plain", "Falta url"); return; }
  backendURL = server.arg("url");
  addLog("Backend actualizado: " + backendURL);
  server.send(200, "text/plain", "Backend: " + backendURL);
}

void handleBorrarPersona() {
  if (!server.hasArg("id")) { server.send(400, "text/plain", "Falta ID"); return; }
  String id = server.arg("id");
  DynamicJsonDocument doc(2048);
  JsonArray arr = loadArray("/personas.json", doc);
  for (JsonArray::iterator it = arr.begin(); it != arr.end(); ++it) {
    if ((*it)["id"].as<String>() == id) {
      int huella = (*it)["huella_id"].as<int>();
      if (huella > 0) finger.deleteModel(huella);
      arr.remove(it);
      saveArray("/personas.json", doc);
      server.send(200, "text/plain", "Persona eliminada");
      return;
    }
  }
  server.send(404, "text/plain", "Persona no encontrada");
}

void handleBorrarTurno() {
  if (!server.hasArg("id")) { server.send(400, "text/plain", "Falta ID"); return; }
  String id = server.arg("id");
  DynamicJsonDocument doc(1024);
  JsonArray arr = loadArray("/turnos.json", doc);
  for (JsonArray::iterator it = arr.begin(); it != arr.end(); ++it) {
    if ((*it)["id"].as<String>() == id) {
      arr.remove(it);
      saveArray("/turnos.json", doc);
      server.send(200, "text/plain", "Turno eliminado");
      return;
    }
  }
  server.send(404, "text/plain", "Turno no encontrado");
}

void handleBorrarAsignacion() {
  if (!server.hasArg("persona") || !server.hasArg("turno")) { server.send(400, "text/plain", "Faltan datos"); return; }
  String persona = server.arg("persona");
  String turno = server.arg("turno");
  DynamicJsonDocument doc(1024);
  JsonArray arr = loadArray("/asignaciones.json", doc);
  for (JsonArray::iterator it = arr.begin(); it != arr.end(); ++it) {
    if ((*it)["persona_id"].as<String>() == persona && (*it)["turno_id"].as<String>() == turno) {
      arr.remove(it);
      saveArray("/asignaciones.json", doc);
      server.send(200, "text/plain", "Asignacion eliminada");
      return;
    }
  }
  server.send(404, "text/plain", "Asignacion no encontrada");
}

void handleUltimoRegistro() {
    DynamicJsonDocument doc(2048);
    JsonArray personas = loadArray("/personas.json", doc);
    if (personas.size() == 0) {
        server.send(404, "application/json", "{\"error\": \"No hay registros\"}");
        return;
    }
    JsonObject lastP = personas[personas.size() - 1];
    String json = "{";
    json += "\"id\":\"" + lastP["id"].as<String>() + "\",";
    json += "\"nombre\":\"" + lastP["nombre"].as<String>() + "\",";
    json += "\"rut\":\"" + lastP["rut"].as<String>() + "\",";
    json += "\"imagen_url\":\"" + lastCapturedImageUrl + "\"";
    json += "}";
    server.send(200, "application/json", json);
}

void handleGetPersonas() { servirArchivo("/personas.json", "application/json"); }
void handleGetTurnos() { servirArchivo("/turnos.json", "application/json"); }
void handleGetAsignaciones() { servirArchivo("/asignaciones.json", "application/json"); }
void handleGetAsistencias() { servirArchivo("/asistencias.json", "application/json"); }

// ============================================================
// SETUP
// ============================================================
void setup() {
  pinMode(13, INPUT_PULLUP);
  if (digitalRead(13) == LOW) {
    delay(1000);
    if (digitalRead(13) == LOW) {
      initSPIFFS(); saveConfig("", "", backendURL, mqttBroker); Serial.println("RESET DETECTADO");
    }
  }
  
  Serial.begin(115200); delay(1000);

  initCamera(); delay(500);
  FingerSerial.begin(57600, SERIAL_8N1, 14, 15);
  finger.begin(57600);
  if (finger.verifyPassword()) addLog("Sensor AS608 conectado");

  initSPIFFS(); delay(500); loadWiFiConfig(); tryConnectWiFi();
  
  if (isOnline) {
    WiFi.setTxPower(WIFI_POWER_8_5dBm); 
    sincronizarPersonasDesdeBackend(); // Obtener BD limpia al arrancar
  } else {
    WiFi.mode(WIFI_AP); WiFi.softAP(apSSID, apPASS, 1, 0, 4);
    WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));
  }

  // Rutas HTML
  server.on("/", []() { servirArchivo("/index.html", "text/html"); });
  server.on("/register", []() { servirArchivo("/register.html", "text/html"); });
  server.on("/gestion", []() { servirArchivo("/gestion.html", "text/html"); });
  server.on("/personas", []() { servirArchivo("/personas.html", "text/html"); });
  server.on("/asistencias", []() { servirArchivo("/asistencias.html", "text/html"); });
  server.on("/turnos", []() { servirArchivo("/turnos.html", "text/html"); });
  server.on("/asignaciones", []() { servirArchivo("/asignaciones.html", "text/html"); });
  server.on("/wifi-setup", []() { servirArchivo("/wifi-setup.html", "text/html"); });
  
  // Rutas de Acción
  server.on("/wifi-config", handleWiFiConfig);
  server.on("/registrar", handleRegisterUser);
  server.on("/crear_turno", handleCreateTurn);
  server.on("/asignar", handleAssignTurn);
  server.on("/marcar", handleMarcarAsistencia);
  server.on("/limpiar", handleLimpiarDatos);
  server.on("/sincronizar", handleSincronizar);
  server.on("/fetch-personas", handleFetchPersonas);
  server.on("/set-backend", handleSetBackend);
  server.on("/borrar_persona", handleBorrarPersona);
  server.on("/borrar_turno", handleBorrarTurno);
  server.on("/borrar_asignacion", handleBorrarAsignacion);
  
  // Rutas API REST
  server.on("/api/personas", handleGetPersonas);
  server.on("/api/turnos", handleGetTurnos);
  server.on("/api/asignaciones", handleGetAsignaciones);
  server.on("/api/asistencias", handleGetAsistencias);
  server.on("/ultimo_registro", handleUltimoRegistro); 

  server.on("/estado", []() {
    String json = "{";
    json += "\"estado\":\""  + String(estadoActual == ESTADO_IDLE ? "idle" : "ocupado") + "\",";
    json += "\"codigo_paso\":" + String(estadoActual) + ",";
    json += "\"intentos_facial\":" + String(intentosFacial) + ",";
    json += "\"online\":"    + String(isOnline ? "true" : "false") + ",";
    json += "\"camara\":"    + String(camaraIniciada ? "true" : "false") + ",";
    json += "\"backend\":\"" + backendURL + "\",";
    json += "\"mqtt\":\""    + mqttBroker + "\"";
    json += "}";
    server.send(200, "application/json", json);
  });
  
  server.begin();
  addLog("Sistema web iniciado.");
}

// ============================================================
// LOOP PRINCIPAL
// ============================================================
void loop() {
  server.handleClient();
  yield(); 

  if (isOnline && mqtt_client == NULL) mantenerConexionMQTT();
  unsigned long ahora = millis();
  
  if (estadoActual != ESTADO_IDLE && estadoActual != ESTADO_PROCESANDO_ASISTENCIA && (ahora - tiempoUltimoEstado) > TIMEOUT_REGISTRO) {
    addLog("Timeout de registro. Volviendo a inactivo."); 
    estadoActual = ESTADO_IDLE;
  }

  // ==========================================================
  // LÓGICA DE ASISTENCIA HÍBRIDA (CENTINELA + HUELLA)
  // ==========================================================
  if (estadoActual == ESTADO_IDLE) {
      
    // 1. MODO CENTINELA (ROSTRO) 
    if (isOnline && (ahora - cooldownAsistencia > COOLDOWN_TIEMPO) && (ahora - lastFaceCheck > FACE_CHECK_INTERVAL)) {
        lastFaceCheck = ahora;
        
        String personaIdEncontrada = identificarPorRostro();
        if (personaIdEncontrada != "") {
            estadoActual = ESTADO_PROCESANDO_ASISTENCIA;
            addLog("Rostro detectado ID: " + personaIdEncontrada);
            
            String res = procesarAsistencia(personaIdEncontrada, "facial");
            addLog(res);
            
            cooldownAsistencia = millis(); 
            estadoActual = ESTADO_IDLE;
        }
    }

    // 2. MODO RESPALDO (HUELLA)
    if ((ahora - cooldownAsistencia > COOLDOWN_TIEMPO) && (ahora - lastFingerCheck > FINGER_CHECK_INTERVAL)) {
      lastFingerCheck = ahora;
      int p = finger.getImage();
      if (p == FINGERPRINT_OK && finger.image2Tz() == FINGERPRINT_OK && finger.fingerSearch() == FINGERPRINT_OK) {
          
          if (finger.fingerID > 0 && (finger.fingerID != lastFingerID || (ahora - lastFingerTime > FINGER_DEBOUNCE))) {
              estadoActual = ESTADO_PROCESANDO_ASISTENCIA;
              addLog("Huella detectada Sensor ID: " + String(finger.fingerID));
              
              String personaId = buscarPersonaPorHuella(finger.fingerID);
              if (personaId != "") {
                  String res = procesarAsistencia(personaId, isOnline ? "huella_online" : "huella_offline");
                  addLog(res);
                  cooldownAsistencia = millis();
              } else {
                  addLog("Huella no vinculada.");
              }
              
              lastFingerID = finger.fingerID;
              lastFingerTime = millis();
              estadoActual = ESTADO_IDLE;
          }
      }
    }
  }

  // ==========================================================
  // FLUJO DE REGISTRO MANUAL
  // ==========================================================
  if (estadoActual == ESTADO_ESPERANDO_HUELLA_REGISTRO) {
    if (finger.getImage() == FINGERPRINT_OK && finger.image2Tz(1) == FINGERPRINT_OK) {
        addLog("Primera huella capturada, retire el dedo.");
        estadoActual = ESTADO_ESPERANDO_SOLTAR_DEDO; 
        tiempoUltimoEstado = millis();
    }
  }
  else if (estadoActual == ESTADO_ESPERANDO_SOLTAR_DEDO) {
    if (finger.getImage() == FINGERPRINT_NOFINGER) {
      addLog("Vuelva a colocar el mismo dedo para verificar.");
      estadoActual = ESTADO_REGISTRO_SEGUNDA_HUELLA;
      tiempoUltimoEstado = millis();
    }
  }
  else if (estadoActual == ESTADO_REGISTRO_SEGUNDA_HUELLA) {
    if (finger.getImage() == FINGERPRINT_OK && finger.image2Tz(2) == FINGERPRINT_OK) {
        if (finger.createModel() == FINGERPRINT_OK && finger.storeModel(slotRegistrando) == FINGERPRINT_OK) {
            addLog("Huella guardada fisicamente. Enviando datos a DB...");
            completarRegistroPersona(); 
        } else {
          addLog("Las huellas no coinciden. Intente de nuevo.");
          estadoActual = ESTADO_ESPERANDO_HUELLA_REGISTRO;
          tiempoUltimoEstado = millis();
        }
    }
  }
  else if (estadoActual == ESTADO_REGISTRO_FACIAL) {
    static unsigned long ultimoIntentoFoto = 0;
    if (ahora - ultimoIntentoFoto > 4000) { 
      ultimoIntentoFoto = ahora;
      intentosFacial++;
      if (intentosFacial > 6) {
        addLog("Se alcanzó el límite de intentos faciales. Volviendo a menú.");
        estadoActual = ESTADO_IDLE;
      } else {
        addLog("Enviando fotografía #" + String(intentosFacial) + " para registro...");
        registrarRostroEnBackend(idParaRostro); 
      }
    }
  }

  static unsigned long lastSync = 0;
  if (isOnline && (ahora - lastSync) > 300000UL) {
    lastSync = ahora;
    sincronizarAsistencias();
  }

  delay(5); 
}
