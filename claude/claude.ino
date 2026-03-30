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

// ===== Backend y MQTT =====
String backendURL     = "http://172.20.10.3:5000";
String mqttBroker     = ""; // Nueva variable para guardar la IP del MQTT
String lastCapturedImageUrl = "";
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
  ESTADO_IDLE = 0,
  ESTADO_ESPERANDO_HUELLA_REGISTRO = 1,
  ESTADO_REGISTRO_SEGUNDA_HUELLA = 2,
  ESTADO_REGISTRO_FACIAL = 3  // <--- NUEVO ESTADO
};

EstadoSistema estadoActual       = ESTADO_IDLE;
int    slotRegistrando           = -1;
String nombreRegistrando         = "";
String rutRegistrando            = "";
String emailRegistrando          = "";
unsigned long tiempoUltimoEstado = 0;
const unsigned long TIMEOUT_REGISTRO = 30000;

// Nuevas variables para el Bucle Facial
int intentosFacial = 0;
String idParaRostro = "";

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
  if (savedSSID.length() == 0) {
    isOnline = false;
    return;
  }
  
  addLog("Conectando WiFi: " + savedSSID);
  
  // Forzamos modo Estación (Cliente) de forma exclusiva primero
  WiFi.mode(WIFI_STA); 
  WiFi.setSleep(false); // Vital para que el iPhone no lo desconecte
  WiFi.begin(savedSSID.c_str(), savedPASS.c_str());
  
  int intentos = 0;
  // Le damos 10 segundos máximo para conectar (20 intentos de 500ms)
  while (WiFi.status() != WL_CONNECTED && intentos < 20) {
    delay(500);
    Serial.print(".");
    intentos++;
  }
  Serial.println();
  
  isOnline = (WiFi.status() == WL_CONNECTED);
  
  if (isOnline) {
    addLog("WiFi conectado exitosamente");
  } else {
    addLog("WiFi no disponible - abortando conexion");
    WiFi.disconnect(); // Limpiamos cualquier intento colgado en la memoria
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
    String responseBody = http.getString();
    DynamicJsonDocument respDoc(512); 
    DeserializationError err = deserializeJson(respDoc, responseBody);
    
    // Si el backend nos responde con JSON y trae 'preview_url'
    if (!err && respDoc.containsKey("preview_url")) {
        lastCapturedImageUrl = respDoc["preview_url"].as<String>();
        Serial.println("URL de vista previa: " + lastCapturedImageUrl);
    } else {
        addLog("Backend no retorno URL de verificacion (Verificar codigo Flask)");
        lastCapturedImageUrl = ""; // Limpiamos si falla
    }
    // ------------------------------------
    http.end();
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
      // Creamos el wifi.json con los 4 campos por defecto
      file.println(String(f) == "/wifi.json"
        ? "{\"ssid\":\"\",\"pass\":\"\",\"backend\":\"http://172.20.10.3:5000\",\"mqtt\":\"\"}"
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
    if (doc.containsKey("ssid")) savedSSID = doc["ssid"].as<String>();
    if (doc.containsKey("pass")) savedPASS = doc["pass"].as<String>();
    if (doc.containsKey("backend")) backendURL = doc["backend"].as<String>();
    if (doc.containsKey("mqtt")) mqttBroker = doc["mqtt"].as<String>();
    file.close();
  }
}
// Nueva función unificada para guardar toda la configuración
void saveConfig(String ssid, String pass, String backend, String mqtt) {
  DynamicJsonDocument doc(512);
  doc["ssid"] = ssid;
  doc["pass"] = pass;
  doc["backend"] = backend;
  doc["mqtt"] = mqtt;
  
  File file = SPIFFS.open("/wifi.json", "w");
  serializeJson(doc, file);
  file.close();

  // Actualizamos las variables globales al instante
  savedSSID = ssid;
  savedPASS = pass;
  backendURL = backend;
  mqttBroker = mqtt;
}

// ============================================================
// SENSOR DE HUELLAS
// ============================================================

int encontrarSlotLibre() {
  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);
  int maxId = 0;
  
  for (JsonObject p : personas) {
    int hId = p["huella_id"].as<int>();
    if (hId > maxId) maxId = hId;
  }
  
  // Si maxId es 0 (no hay nadie), retorna 1. Si no, retorna el siguiente libre.
  int siguienteLibre = maxId + 1;
  if (siguienteLibre > 127) return -1; // Límite del sensor
  return siguienteLibre;
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
// Guarda la persona en PostgreSQL, en JSON local y pasa al estado facial
void completarRegistroPersona() {
  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);

  String idReal = String(personas.size() + 1); 

  if (isOnline) {
    addLog("Guardando usuario en BD...");
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
      if (respDoc.containsKey("id")) idReal = respDoc["id"].as<String>();
    }
    http.end();
  }

  JsonObject p = personas.createNestedObject();
  p["id"]             = idReal;
  p["nombre"]         = nombreRegistrando;
  p["rut"]            = rutRegistrando;
  p["email"]          = emailRegistrando;
  p["huella_id"]      = slotRegistrando;
  p["fecha_registro"] = getTimestamp();
  p["sincronizado"]   = isOnline;
  saveArray("/personas.json", doc);

  // === PREPARAR EL BUCLE FACIAL ===
  if (camaraIniciada && isOnline) {
    addLog("Iniciando Bucle de Captura Facial...");
    idParaRostro = idReal;
    intentosFacial = 0;
    estadoActual = ESTADO_REGISTRO_FACIAL; // Cambia el estado para que el loop() tome el control
    tiempoUltimoEstado = millis();
  } else {
    addLog("Sin cámara o WiFi. Registro finalizado sin rostro.");
    estadoActual = ESTADO_IDLE; 
  }

  // Limpiar RAM
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

// ======================= BORRAR DATOS INDIVIDUALES =======================
// ... Sección HANDLERS WEB ...

void handleUltimoRegistro() {
    // Buscamos la última persona en personas.json
    DynamicJsonDocument doc(2048);
    JsonArray personas = loadArray("/personas.json", doc);
    if (personas.size() == 0) {
        server.send(404, "application/json", "{\"error\": \"No hay registros\"}");
        return;
    }
    JsonObject lastP = personas[personas.size() - 1];
    
    // Armamos el JSON con los datos locales + la URL de imagen capturada de Flask
    String json = "{";
    json += "\"id\":\"" + lastP["id"].as<String>() + "\",";
    json += "\"nombre\":\"" + lastP["nombre"].as<String>() + "\",";
    json += "\"rut\":\"" + lastP["rut"].as<String>() + "\",";
    json += "\"imagen_url\":\"" + lastCapturedImageUrl + "\"";
    json += "}";
    server.send(200, "application/json", json);
}


void handleBorrarPersona() {
  if (!server.hasArg("id")) { server.send(400, "text/plain", "Falta ID"); return; }
  String id = server.arg("id");
  DynamicJsonDocument doc(2048);
  JsonArray arr = loadArray("/personas.json", doc);
  
  for (JsonArray::iterator it = arr.begin(); it != arr.end(); ++it) {
    if ((*it)["id"].as<String>() == id) {
      int huella = (*it)["huella_id"].as<int>();
      // ¡Crucial! Borrar la huella de la memoria del sensor AS608
      if (huella > 0) finger.deleteModel(huella); 
      
      arr.remove(it); // Eliminar del JSON
      saveArray("/personas.json", doc);
      server.send(200, "text/plain", "Persona y huella eliminadas localmente");
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
  if (!server.hasArg("persona") || !server.hasArg("turno")) { 
      server.send(400, "text/plain", "Faltan datos"); return; 
  }
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
    // Si no envían backend o mqtt, mantenemos los actuales para no borrarlos por error
    String b = server.hasArg("backend") ? server.arg("backend") : backendURL;
    String m = server.hasArg("mqtt") ? server.arg("mqtt") : mqttBroker;
    
    saveConfig(server.arg("ssid"), server.arg("pass"), b, m);
    
    server.send(200, "text/plain", "Configuracion general guardada. Reiniciando equipo...");
    delay(1500);
    ESP.restart();
  } else {
    server.send(400, "text/plain", "Faltan parametros (SSID o Password)");
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

// ============================================================
// SETUP
// ============================================================

void setup() {
  pinMode(13, INPUT_PULLUP); // Configuramos el pin 13 con resistencia interna
  
  // Si al arrancar el pin 13 esta unido a GND (puente físico)
  if (digitalRead(13) == LOW) {
    delay(1000); // Debounce simple
    if (digitalRead(13) == LOW) {
      initSPIFFS(); // Aseguramos que SPIFFS este listo
      saveConfig("", "", backendURL, mqttBroker); // Borramos el WiFi y conservamos servers
      Serial.println("¡RESET DE WIFI DETECTADO POR HARDWARE!");
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

  // 3. SPIFFS y Configuraciones
  initSPIFFS();
  delay(500);
  loadWiFiConfig();

  // 4. WiFi externo (Modo Exclusivo STA)
  tryConnectWiFi();

  // 5. Decisión de Arquitectura: STA Exclusivo o AP de Rescate
  if (isOnline) {
    // Logró conectar a tu iPhone/Router
    addLog("Operando en Modo Cliente (STA). AP desactivado.");
    addLog("IP Asignada: " + WiFi.localIP().toString());
  } else {
    // Falló la conexión o no hay credenciales guardadas
    addLog("Iniciando Modo Offline (AP de Rescate)...");
    WiFi.mode(WIFI_AP);
    WiFi.setTxPower(WIFI_POWER_11dBm);
    WiFi.softAP(apSSID, apPASS, 1, 0, 4);
    WiFi.softAPConfig(
      IPAddress(192, 168, 4, 1),
      IPAddress(192, 168, 4, 1),
      IPAddress(255, 255, 255, 0)
    );
    addLog("Red AP Levantada: " + String(apSSID));
    addLog("IP de configuracion: " + WiFi.softAPIP().toString());
  }

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
  server.on("/borrar_persona", handleBorrarPersona);
  server.on("/borrar_turno",   handleBorrarTurno);
  server.on("/borrar_asignacion", handleBorrarAsignacion);

  // 8. APIs REST
  server.on("/api/personas",     handleGetPersonas);
  server.on("/api/turnos",       handleGetTurnos);
  server.on("/api/asignaciones", handleGetAsignaciones);
  server.on("/api/asistencias",  handleGetAsistencias);
  server.on("/ultimo_registro",  handleUltimoRegistro); // <--- Vital para ver la foto

  // 9. Estado del sistema en JSON
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
  addLog("Sistema listo.");
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
            completarRegistroPersona(); // <--- Esto cambiará el estado automáticamente a FACIAL
            return; // Salimos inmediatamente
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
    }
    estadoActual = ESTADO_IDLE; // Si hubo un error irrecuperable
    return;
  }

  // ===== Registro: Captura Facial Iterativa (NUEVO) =====
  if (estadoActual == ESTADO_REGISTRO_FACIAL) {
    unsigned long ahoraLoop = millis();
    static unsigned long ultimoIntentoFoto = 0;
    
    // Intenta tomar una foto cada 2.5 segundos
    if (ahoraLoop - ultimoIntentoFoto > 2500) {
      ultimoIntentoFoto = ahoraLoop;
      intentosFacial++;
      addLog("Intento facial #" + String(intentosFacial) + " de 6...");
      
      bool exito = registrarRostroEnBackend(idParaRostro);
      
      if (exito) {
        addLog("¡Rostro detectado y guardado exitosamente!");
        estadoActual = ESTADO_IDLE; // Termina feliz
      } else {
        if (intentosFacial >= 6) {
          addLog("Límite de intentos alcanzado. Registro completado sin rostro.");
          estadoActual = ESTADO_IDLE; // Se rinde tras 6 fotos malas
        } else {
          addLog("Rostro no detectado. Reintentando captura...");
        }
      }
      tiempoUltimoEstado = millis(); // Evita que se cancele por timeout general
    }
    return;
  }

  // Sincronizacion automatica cada 5 minutos si hay conexion
  static unsigned long lastSync = 0;
  if (isOnline && (ahora - lastSync) > 300000UL) {
    lastSync = ahora;
    sincronizarAsistencias();
  }
}
