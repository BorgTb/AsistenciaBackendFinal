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

#define FLASH_PIN 4

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
unsigned long bloqueoAsistenciaHasta = 0;
const unsigned long BLOQUEO_MENU_MS = 90000;
bool baselineMovimientoLista = false;
uint32_t firmaMovimientoAnterior = 0;
const uint32_t UMBRAL_MOVIMIENTO = 1800;
bool rostroRegistroExitoso = false;
String ultimoErrorRegistro = "";

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
bool modoEdicionHuella = false;
bool modoEdicionRostro = false;
String personaEditandoId = "";
int huellaAnteriorEditando = -1;
unsigned long ultimoLogDiagnosticoOffline = 0;

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
void actualizarBloqueoAsistencia(unsigned long duracionMs = BLOQUEO_MENU_MS);
bool asistenciaAutomaticaHabilitada(unsigned long ahora);
bool detectarMovimientoCamara();
uint32_t calcularFirmaMovimiento(const uint8_t* data, size_t len);
String jsonEscape(const String& src);
bool datosOfflineListos(String& motivo);
String motivoAsistenciaAutomatica(unsigned long ahora);
void flashExito();
void flashError();
bool resultadoAsistenciaExitosa(const String& resultado);

void handleWiFiConfig();
void handleRegisterUser();
void handleCreateTurn();
void handleAssignTurn();
void handleMarcarAsistencia();
void handleLimpiarDatos();
void handleSincronizar();
void handleFetchPersonas();
void handleSetBackend();
void handleEditarPersona();
void handleActualizarHuellaPersona();
void handleActualizarRostroPersona();
void handleBorrarPersona();
void handleBorrarTurno();
void handleBorrarAsignacion();
void handleGetPersonas();
void handleGetTurnos();
void handleGetAsignaciones();
void handleGetAsistencias();
void handleUltimoRegistro();
void servirArchivo(const char* path, const char* tipo);
void completarEdicionHuellaExistente();

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
          rostroRegistroExitoso = true;
          ultimoErrorRegistro = "";
          estadoActual = ESTADO_IDLE;
          nombreRegistrando = "";
          rutRegistrando = "";
          emailRegistrando = "";
          slotRegistrando = -1;
          idParaRostro = "";
          modoEdicionRostro = false;
          personaEditandoId = "";
        } else {
          String detalle = doc["mensaje"].as<String>();
          addLog("Rostro rechazado: " + detalle);
          ultimoErrorRegistro = "Rostro rechazado: " + detalle;
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

void flashExito() {   // 2 destellos rapidos = OK
  for (int i = 0; i < 2; i++) {
    digitalWrite(FLASH_PIN, HIGH); delay(150);
    digitalWrite(FLASH_PIN, LOW);  delay(150);
  }
}

void flashError() {   // 1 destello largo = error
  digitalWrite(FLASH_PIN, HIGH); delay(800);
  digitalWrite(FLASH_PIN, LOW);
}

bool resultadoAsistenciaExitosa(const String& resultado) {
  return resultado.indexOf(" OK: ") >= 0;
}

unsigned long getTimestamp() {
  if (bootEpoch > 0) return bootEpoch + millis() / 1000;
  return millis() / 1000;
}

void actualizarBloqueoAsistencia(unsigned long duracionMs) {
  unsigned long nuevoBloqueo = millis() + duracionMs;
  if (nuevoBloqueo > bloqueoAsistenciaHasta) bloqueoAsistenciaHasta = nuevoBloqueo;
}

bool asistenciaAutomaticaHabilitada(unsigned long ahora) {
  return motivoAsistenciaAutomatica(ahora) == "habilitada";
}

bool datosOfflineListos(String& motivo) {
  DynamicJsonDocument docPersonas(2048);
  JsonArray personas = loadArray("/personas.json", docPersonas);
  if (personas.size() == 0) {
    motivo = "sin_personas_locales";
    return false;
  }

  DynamicJsonDocument docAsignaciones(1024);
  JsonArray asignaciones = loadArray("/asignaciones.json", docAsignaciones);
  if (asignaciones.size() == 0) {
    motivo = "sin_asignaciones_locales";
    return false;
  }

  motivo = "habilitada";
  return true;
}

String motivoAsistenciaAutomatica(unsigned long ahora) {
  if (estadoActual != ESTADO_IDLE) return "sistema_ocupado";
  if (ahora - cooldownAsistencia <= COOLDOWN_TIEMPO) return "cooldown";

  if (!isOnline) {
    String motivo = "";
    if (!datosOfflineListos(motivo)) return motivo;
    return "habilitada";
  }

  if (ahora < bloqueoAsistenciaHasta) return "bloqueo_menu";
  return "habilitada";
}

uint32_t calcularFirmaMovimiento(const uint8_t* data, size_t len) {
  if (!data || len == 0) return 0;
  const size_t muestras = 128;
  size_t salto = len / muestras;
  if (salto == 0) salto = 1;

  uint32_t acumulador = 0;
  for (size_t i = 0, tomadas = 0; i < len && tomadas < muestras; i += salto, tomadas++) {
    acumulador += data[i];
  }
  return acumulador;
}

String jsonEscape(const String& src) {
  String out = "";
  out.reserve(src.length() + 8);
  for (size_t i = 0; i < src.length(); i++) {
    char c = src[i];
    if (c == '\\') out += "\\\\";
    else if (c == '"') out += "\\\"";
    else if (c == '\n') out += "\\n";
    else if (c == '\r') out += "\\r";
    else if (c == '\t') out += "\\t";
    else out += c;
  }
  return out;
}

bool detectarMovimientoCamara() {
  if (!camaraIniciada) return false;

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return false;

  uint32_t firmaActual = calcularFirmaMovimiento(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  if (!baselineMovimientoLista) {
    baselineMovimientoLista = true;
    firmaMovimientoAnterior = firmaActual;
    return false;
  }

  long delta = (long)firmaActual - (long)firmaMovimientoAnterior;
  if (delta < 0) delta = -delta;

  firmaMovimientoAnterior = (firmaMovimientoAnterior * 3 + firmaActual) / 4;
  return (uint32_t)delta >= UMBRAL_MOVIMIENTO;
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
    baselineMovimientoLista = false;
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
  bool tieneEsquema = brokerUrl.startsWith("mqtt://") || brokerUrl.startsWith("ws://") || brokerUrl.startsWith("wss://") ||
                     brokerUrl.startsWith("http://") || brokerUrl.startsWith("https://");

  if (!tieneEsquema) {
    if (brokerUrl.indexOf(":") == -1) brokerUrl += ":1883";
    brokerUrl = "mqtt://" + brokerUrl;
  } else {
    if (brokerUrl.startsWith("http://")) brokerUrl = "ws://" + brokerUrl.substring(7);
    else if (brokerUrl.startsWith("https://")) brokerUrl = "wss://" + brokerUrl.substring(8);

    if (brokerUrl.startsWith("ws://") || brokerUrl.startsWith("wss://")) {
      if (!brokerUrl.endsWith("/mqtt")) brokerUrl += brokerUrl.endsWith("/") ? "mqtt" : "/mqtt";
    }
  }

  addLog("Conectando MQTT: " + brokerUrl);
  esp_mqtt_client_config_t mqtt_cfg = {};
  
  #if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
    mqtt_cfg.broker.address.uri = brokerUrl.c_str();
    if (brokerUrl.startsWith("wss://")) {
      mqtt_cfg.broker.verification.crt_bundle_attach = esp_crt_bundle_attach;
    }
  #else
    mqtt_cfg.uri = brokerUrl.c_str();
    if (brokerUrl.startsWith("wss://")) {
      mqtt_cfg.crt_bundle_attach = esp_crt_bundle_attach;
    }
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
  ultimoErrorRegistro = "";
  rostroRegistroExitoso = false;

  String idReal = "";
  bool personaCreadaEnBackend = false;

  if (isOnline && WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(backendURL + "/api/personas");
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(10000);

    DynamicJsonDocument bodyDoc(512);
    bodyDoc["nombre"] = nombreRegistrando;
    bodyDoc["rut"] = rutRegistrando;
    bodyDoc["email"] = emailRegistrando;
    bodyDoc["huella_id"] = slotRegistrando;
    String payload;
    serializeJson(bodyDoc, payload);

    int httpCode = http.POST(payload);
    if (httpCode == 200 || httpCode == 201) {
      String response = http.getString();
      DynamicJsonDocument respDoc(256);
      DeserializationError err = deserializeJson(respDoc, response);
      if (!err && respDoc.containsKey("id")) {
        idReal = respDoc["id"].as<String>();
        personaCreadaEnBackend = true;
        addLog("Usuario creado en BD ID: " + idReal);
      } else {
        addLog("Advertencia: backend no devolvio ID. Guardando registro local.");
      }
    } else {
      addLog("Advertencia BD (Cod:" + String(httpCode) + "). Guardando registro local.");
    }
    http.end();
  } else {
    addLog("Sin internet: guardando persona solo en memoria local.");
  }

  if (idReal == "") {
    idReal = "local-" + String(getTimestamp()) + "-" + String(slotRegistrando);
  }

  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);
  JsonObject p = personas.createNestedObject();
  p["id"]             = idReal;
  p["nombre"]         = nombreRegistrando;
  p["rut"]            = rutRegistrando;
  p["email"]          = emailRegistrando;
  p["huella_id"]      = slotRegistrando;
  p["fecha_registro"] = getTimestamp();
  p["sincronizado"]   = personaCreadaEnBackend;
  saveArray("/personas.json", doc);
  
  if (personaCreadaEnBackend && camaraIniciada) {
    addLog("Mire a la cámara para la foto...");
    idParaRostro = idReal;   
    intentosFacial = 0;      
    actualizarBloqueoAsistencia(120000);
    estadoActual = ESTADO_REGISTRO_FACIAL;
    tiempoUltimoEstado = millis();
  } else {
    if (!personaCreadaEnBackend) {
      addLog("Registro local completado (pendiente de sincronizacion con backend).");
    }
    rostroRegistroExitoso = true;
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
    actualizarBloqueoAsistencia(120000);
    saveConfig(server.arg("ssid"), server.arg("pass"), server.hasArg("backend") ? server.arg("backend") : backendURL, server.hasArg("mqtt") ? server.arg("mqtt") : mqttBroker);
    server.send(200, "text/plain", "Guardado. Reiniciando...");
    delay(1500); ESP.restart();
  } else { server.send(400, "text/plain", "Faltan parametros"); }
}

void handleRegisterUser() {
  if (!server.hasArg("name") || !server.hasArg("rut")) { server.send(400, "text/plain", "Faltan datos"); return; }
  ultimoErrorRegistro = "";
  rostroRegistroExitoso = false;
  actualizarBloqueoAsistencia(120000);
  int slot = encontrarSlotLibre();
  if (slot < 0) { server.send(500, "text/plain", "Sin slots"); return; }
  slotRegistrando = slot; nombreRegistrando = server.arg("name"); rutRegistrando = server.arg("rut"); emailRegistrando = server.arg("email");
  estadoActual = ESTADO_ESPERANDO_HUELLA_REGISTRO; tiempoUltimoEstado = millis();
  server.send(200, "text/plain", "OK: Ponga el dedo...");
}

void handleCreateTurn() {
  actualizarBloqueoAsistencia();
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
  actualizarBloqueoAsistencia();
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
  actualizarBloqueoAsistencia(30000);
  addLog("Esperando huella...");
  int p = finger.getImage();
  if (p != FINGERPRINT_OK) {
    flashError();
    server.send(500, "text/plain", "No se detecta huella");
    return;
  }
  if (finger.image2Tz() != FINGERPRINT_OK) {
    flashError();
    server.send(500, "text/plain", "Error procesando imagen");
    return;
  }
  if (finger.fingerSearch() != FINGERPRINT_OK) {
    flashError();
    server.send(500, "text/plain", "Huella no encontrada");
    return;
  }
  String pId = buscarPersonaPorHuella(finger.fingerID);
  String resultado = procesarAsistencia(pId, "huella_manual");
  if (resultadoAsistenciaExitosa(resultado)) flashExito();
  else flashError();
  server.send(200, "text/plain", resultado);
}

void handleLimpiarDatos() {
  actualizarBloqueoAsistencia(120000);
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
  actualizarBloqueoAsistencia();
  if (!isOnline) { server.send(503, "text/plain", "Sin conexion"); return; }
  sincronizarAsistencias();
  server.send(200, "text/plain", "Sincronizacion ejecutada");
}

void handleFetchPersonas() {
  actualizarBloqueoAsistencia();
  if (!isOnline) { server.send(503, "text/plain", "Sin conexion WiFi"); return; }
  sincronizarPersonasDesdeBackend();
  server.send(200, "text/plain", "Personas obtenidas. Revisa los logs.");
}

void handleSetBackend() {
  actualizarBloqueoAsistencia(120000);
  if (!server.hasArg("url")) { server.send(400, "text/plain", "Falta url"); return; }
  backendURL = server.arg("url");
  addLog("Backend actualizado: " + backendURL);
  server.send(200, "text/plain", "Backend: " + backendURL);
}

void handleEditarPersona() {
  actualizarBloqueoAsistencia(120000);
  if (!server.hasArg("id") || !server.hasArg("name")) {
    server.send(400, "text/plain", "Faltan id o name");
    return;
  }

  String id = server.arg("id");
  String nuevoNombre = server.arg("name");
  String nuevoEmail = server.hasArg("email") ? server.arg("email") : "";
  nuevoNombre.trim();
  nuevoEmail.trim();

  if (nuevoNombre.length() == 0) {
    server.send(400, "text/plain", "Nombre invalido");
    return;
  }

  DynamicJsonDocument doc(4096);
  JsonArray arr = loadArray("/personas.json", doc);
  JsonObject objetivo;
  bool encontrado = false;
  for (JsonObject p : arr) {
    if (p["id"].as<String>() == id) {
      objetivo = p;
      encontrado = true;
      break;
    }
  }

  if (!encontrado) {
    server.send(404, "text/plain", "Persona no encontrada local");
    return;
  }

  objetivo["nombre"] = nuevoNombre;
  objetivo["email"] = nuevoEmail;
  objetivo["sincronizado"] = false;

  bool synced = false;
  if (isOnline && WiFi.status() == WL_CONNECTED && !id.startsWith("local-")) {
    HTTPClient http;
    http.begin(backendURL + "/api/personas/" + id);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(10000);

    DynamicJsonDocument payloadDoc(512);
    payloadDoc["nombre"] = nuevoNombre;
    payloadDoc["email"] = nuevoEmail;
    String payload;
    serializeJson(payloadDoc, payload);

    int code = http.sendRequest("PATCH", payload);
    if (code == 200) {
      synced = true;
      objetivo["sincronizado"] = true;
      addLog("Persona editada y sincronizada: " + id);
    } else {
      addLog("Edicion local OK, backend pendiente. Codigo: " + String(code));
    }
    http.end();
  } else {
    addLog("Edicion local guardada (sin backend disponible)");
  }

  saveArray("/personas.json", doc);
  server.send(200, "text/plain", synced ? "Persona actualizada y sincronizada" : "Persona actualizada local (pendiente sync)");
}

void handleActualizarHuellaPersona() {
  actualizarBloqueoAsistencia(120000);
  if (!server.hasArg("id")) {
    server.send(400, "text/plain", "Falta id");
    return;
  }
  if (estadoActual != ESTADO_IDLE) {
    server.send(409, "text/plain", "Sistema ocupado, intente de nuevo");
    return;
  }

  String id = server.arg("id");
  DynamicJsonDocument doc(4096);
  JsonArray arr = loadArray("/personas.json", doc);

  JsonObject objetivo;
  bool encontrado = false;
  for (JsonObject p : arr) {
    if (p["id"].as<String>() == id) {
      objetivo = p;
      encontrado = true;
      break;
    }
  }

  if (!encontrado) {
    server.send(404, "text/plain", "Persona no encontrada local");
    return;
  }

  int slot = encontrarSlotLibre();
  if (slot < 0) {
    server.send(500, "text/plain", "Sin slots de huella disponibles");
    return;
  }

  int viejaHuella = objetivo["huella_id"].as<int>();
  if (viejaHuella > 0) finger.deleteModel(viejaHuella);

  modoEdicionHuella = true;
  personaEditandoId = id;
  huellaAnteriorEditando = viejaHuella;
  slotRegistrando = slot;
  estadoActual = ESTADO_ESPERANDO_HUELLA_REGISTRO;
  tiempoUltimoEstado = millis();

  server.send(200, "text/plain", "OK: Coloque el dedo para actualizar huella");
}

void handleActualizarRostroPersona() {
  actualizarBloqueoAsistencia(120000);
  if (!server.hasArg("id")) {
    server.send(400, "text/plain", "Falta id");
    return;
  }
  if (estadoActual != ESTADO_IDLE) {
    server.send(409, "text/plain", "Sistema ocupado, intente de nuevo");
    return;
  }

  String id = server.arg("id");
  if (id.startsWith("local-")) {
    server.send(409, "text/plain", "Persona local sin ID remoto, sincronice primero");
    return;
  }
  if (!isOnline || WiFi.status() != WL_CONNECTED) {
    server.send(503, "text/plain", "Sin conexion para actualizar rostro");
    return;
  }

  modoEdicionRostro = true;
  personaEditandoId = id;
  idParaRostro = id;
  intentosFacial = 0;
  rostroRegistroExitoso = false;
  ultimoErrorRegistro = "";
  estadoActual = ESTADO_REGISTRO_FACIAL;
  tiempoUltimoEstado = millis();

  server.send(200, "text/plain", "Mire a la camara para actualizar rostro");
}

void completarEdicionHuellaExistente() {
  if (!modoEdicionHuella || personaEditandoId.length() == 0 || slotRegistrando <= 0) {
    estadoActual = ESTADO_IDLE;
    return;
  }

  DynamicJsonDocument doc(4096);
  JsonArray arr = loadArray("/personas.json", doc);
  JsonObject objetivo;
  bool encontrado = false;
  for (JsonObject p : arr) {
    if (p["id"].as<String>() == personaEditandoId) {
      objetivo = p;
      encontrado = true;
      break;
    }
  }

  if (!encontrado) {
    addLog("No se encontro persona para actualizar huella");
    estadoActual = ESTADO_IDLE;
    modoEdicionHuella = false;
    personaEditandoId = "";
    slotRegistrando = -1;
    huellaAnteriorEditando = -1;
    return;
  }

  objetivo["huella_id"] = slotRegistrando;
  objetivo["sincronizado"] = false;
  bool synced = false;

  if (isOnline && WiFi.status() == WL_CONNECTED && !personaEditandoId.startsWith("local-")) {
    HTTPClient http;
    http.begin(backendURL + "/api/personas/" + personaEditandoId + "/huella");
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(10000);

    DynamicJsonDocument payloadDoc(256);
    payloadDoc["huella_id"] = slotRegistrando;
    String payload;
    serializeJson(payloadDoc, payload);

    int code = http.sendRequest("PUT", payload);
    if (code == 200) {
      synced = true;
      objetivo["sincronizado"] = true;
    } else {
      addLog("Huella local actualizada, backend pendiente. Codigo: " + String(code));
    }
    http.end();
  }

  saveArray("/personas.json", doc);
  addLog(synced ? "Huella actualizada y sincronizada" : "Huella actualizada localmente");

  modoEdicionHuella = false;
  personaEditandoId = "";
  slotRegistrando = -1;
  huellaAnteriorEditando = -1;
  estadoActual = ESTADO_IDLE;
}

void handleBorrarPersona() {
  actualizarBloqueoAsistencia();
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
  actualizarBloqueoAsistencia();
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
  actualizarBloqueoAsistencia();
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
  actualizarBloqueoAsistencia(120000);
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

void handleGetPersonas() { actualizarBloqueoAsistencia(); servirArchivo("/personas.json", "application/json"); }
void handleGetTurnos() { actualizarBloqueoAsistencia(); servirArchivo("/turnos.json", "application/json"); }
void handleGetAsignaciones() { actualizarBloqueoAsistencia(); servirArchivo("/asignaciones.json", "application/json"); }
void handleGetAsistencias() { actualizarBloqueoAsistencia(); servirArchivo("/asistencias.json", "application/json"); }

// ============================================================
// SETUP
// ============================================================
void setup() {
  pinMode(13, INPUT_PULLUP);
  pinMode(FLASH_PIN, OUTPUT);
  digitalWrite(FLASH_PIN, LOW);
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
  server.on("/", []() { actualizarBloqueoAsistencia(); servirArchivo("/index.html", "text/html"); });
  server.on("/register", []() { actualizarBloqueoAsistencia(120000); servirArchivo("/register.html", "text/html"); });
  server.on("/gestion", []() { actualizarBloqueoAsistencia(); servirArchivo("/gestion.html", "text/html"); });
  server.on("/personas", []() { actualizarBloqueoAsistencia(); servirArchivo("/personas.html", "text/html"); });
  server.on("/asistencias", []() { actualizarBloqueoAsistencia(); servirArchivo("/asistencias.html", "text/html"); });
  server.on("/turnos", []() { actualizarBloqueoAsistencia(); servirArchivo("/turnos.html", "text/html"); });
  server.on("/asignaciones", []() { actualizarBloqueoAsistencia(); servirArchivo("/asignaciones.html", "text/html"); });
  server.on("/wifi-setup", []() { actualizarBloqueoAsistencia(120000); servirArchivo("/wifi-setup.html", "text/html"); });
  server.on("/logs", []() { servirArchivo("/logs.html", "text/html"); });
  
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
  server.on("/editar_persona", handleEditarPersona);
  server.on("/actualizar_huella", handleActualizarHuellaPersona);
  server.on("/actualizar_rostro", handleActualizarRostroPersona);
  server.on("/borrar_persona", handleBorrarPersona);
  server.on("/borrar_turno", handleBorrarTurno);
  server.on("/borrar_asignacion", handleBorrarAsignacion);
  
  // Rutas API REST
  server.on("/api/personas", handleGetPersonas);
  server.on("/api/turnos", handleGetTurnos);
  server.on("/api/asignaciones", handleGetAsignaciones);
  server.on("/api/asistencias", handleGetAsistencias);
  server.on("/api/logs", []() {
    String contenido = logBuffer;
    if (contenido.length() == 0) contenido = "Sin logs disponibles";
    server.send(200, "text/html", contenido);
  });
  server.on("/api/logs/clear", []() {
    logBuffer = "";
    server.send(200, "text/plain", "Logs limpiados");
  });
  server.on("/ultimo_registro", handleUltimoRegistro); 

  server.on("/estado", []() {
    String referer = server.header("Referer");
    if (referer.indexOf("/register") >= 0 || referer.indexOf("/wifi-setup") >= 0 ||
        (referer.indexOf("/gestion") >= 0 && estadoActual != ESTADO_IDLE)) {
      actualizarBloqueoAsistencia();
    }

    DynamicJsonDocument docPersonas(2048);
    DynamicJsonDocument docAsignaciones(1024);
    DynamicJsonDocument docAsistencias(2048);
    JsonArray personas = loadArray("/personas.json", docPersonas);
    JsonArray asignaciones = loadArray("/asignaciones.json", docAsignaciones);
    JsonArray asistencias = loadArray("/asistencias.json", docAsistencias);
    String motivoAuto = motivoAsistenciaAutomatica(millis());

    String json = "{";
    json += "\"estado\":\""  + String(estadoActual == ESTADO_IDLE ? "idle" : "ocupado") + "\",";
    json += "\"codigo_paso\":" + String(estadoActual) + ",";
    json += "\"intentos_facial\":" + String(intentosFacial) + ",";
    json += "\"online\":"    + String(isOnline ? "true" : "false") + ",";
    json += "\"camara\":"    + String(camaraIniciada ? "true" : "false") + ",";
    json += "\"rostro_ok\":" + String(rostroRegistroExitoso ? "true" : "false") + ",";
    json += "\"error_registro\":\"" + jsonEscape(ultimoErrorRegistro) + "\",";
    json += "\"asistencia_bloqueada\":" + String(millis() < bloqueoAsistenciaHasta ? "true" : "false") + ",";
    json += "\"bloqueo_restante_ms\":" + String(millis() < bloqueoAsistenciaHasta ? (bloqueoAsistenciaHasta - millis()) : 0) + ",";
    json += "\"asistencia_auto_huella_habilitada\":" + String(motivoAuto == "habilitada" ? "true" : "false") + ",";
    json += "\"motivo_asistencia_auto\":\"" + motivoAuto + "\",";
    json += "\"personas_locales\":" + String(personas.size()) + ",";
    json += "\"asignaciones_locales\":" + String(asignaciones.size()) + ",";
    json += "\"asistencias_locales\":" + String(asistencias.size()) + ",";
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
    String motivoAuto = motivoAsistenciaAutomatica(ahora);
    if (!isOnline && motivoAuto != "habilitada" && (ahora - ultimoLogDiagnosticoOffline) > 15000) {
      ultimoLogDiagnosticoOffline = ahora;
      addLog("[OFFLINE] Auto-huella inactiva: " + motivoAuto);
    }
      
    // 1. MODO CENTINELA (ROSTRO) 
    if (isOnline && asistenciaAutomaticaHabilitada(ahora) && (ahora - lastFaceCheck > FACE_CHECK_INTERVAL)) {
        lastFaceCheck = ahora;

      if (detectarMovimientoCamara()) {
        addLog("Movimiento detectado. Ejecutando reconocimiento facial...");
        String personaIdEncontrada = identificarPorRostro();
        if (personaIdEncontrada != "") {
          estadoActual = ESTADO_PROCESANDO_ASISTENCIA;
          addLog("Rostro detectado ID: " + personaIdEncontrada);

          String res = procesarAsistencia(personaIdEncontrada, "facial");
          addLog(res);
          if (resultadoAsistenciaExitosa(res)) flashExito();
          else flashError();

          cooldownAsistencia = millis();
          estadoActual = ESTADO_IDLE;
        }
        }
    }

    // 2. MODO RESPALDO (HUELLA)
    if (asistenciaAutomaticaHabilitada(ahora) && (ahora - lastFingerCheck > FINGER_CHECK_INTERVAL)) {
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
                  if (resultadoAsistenciaExitosa(res)) flashExito();
                  else flashError();
                  cooldownAsistencia = millis();
              } else {
                  addLog("Huella no vinculada.");
                  flashError();
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
            if (modoEdicionHuella) completarEdicionHuellaExistente();
            else completarRegistroPersona(); 
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
        ultimoErrorRegistro = "No se pudo registrar rostro tras multiples intentos";
        estadoActual = ESTADO_IDLE;
        nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = ""; slotRegistrando = -1;
        idParaRostro = "";
        modoEdicionRostro = false;
        personaEditandoId = "";
      } else {
        addLog("Enviando fotografía #" + String(intentosFacial) + " para registro...");
        if (!registrarRostroEnBackend(idParaRostro)) {
          addLog("No se pudo enviar foto por MQTT. Reintentando...");
          if (mqtt_client == NULL && mqttBroker != "") mantenerConexionMQTT();
        }
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
