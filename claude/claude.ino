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
#include "mqtt_client.h"
#include "esp_crt_bundle.h" // <--- NUEVO: Librería de certificados de fábrica del ESP32



esp_mqtt_client_handle_t mqtt_client = NULL;
bool mqttConnected = false;

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
String backendURL     = "https://sculpture-kong-filtering-essential.trycloudflare.com";
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
  ESTADO_ESPERANDO_SOLTAR_DEDO = 4, // <--- NUEVO ESTADO
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
static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data) {
  esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
  
  switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
      addLog("¡MQTT Conectado por WebSockets!");
      mqttConnected = true;
      // Nos suscribimos a la respuesta del backend
      esp_mqtt_client_subscribe(mqtt_client, "esp32/respuesta/facial", 0);
      break;
      
    case MQTT_EVENT_DISCONNECTED:
      addLog("MQTT Desconectado");
      mqttConnected = false;
      break;
      
    case MQTT_EVENT_DATA: {
      String topic = String(event->topic).substring(0, event->topic_len);
      String mensaje = String(event->data).substring(0, event->data_len);
      
      if (topic == "esp32/respuesta/facial") {
        DynamicJsonDocument doc(512);
        deserializeJson(doc, mensaje);
        
        if (doc["status"] == "ok") {
          addLog("¡Backend confirmó rostro OK!");
          String fileName = doc["file_name"].as<String>();
          String urlBase = backendURL;
          if (urlBase.endsWith("/")) urlBase = urlBase.substring(0, urlBase.length() - 1);
          lastCapturedImageUrl = urlBase + "/static/previews/" + fileName;
          estadoActual = ESTADO_IDLE; // Terminamos el registro
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
    addLog("Camara iniciada correctamente");
  } else {
    addLog("Error iniciando camara - continuando sin camara");
  }
  sensor_t * s = esp_camera_sensor_get();
  s->set_brightness(s, 1);     // Rango: -2 a 2 (Sube un poco el brillo)
  s->set_contrast(s, 1);       // Rango: -2 a 2 (Aumenta el contraste para definir rasgos)
  s->set_special_effect(s, 0); // 0 = Sin efecto
  s->set_vflip(s, 1);          // Si la imagen llega invertida, usa 1 para voltearla
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
  
  int contador_wdt = 0; // NUEVO CONTADOR

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
    
    // NUEVO: Cada 500 bytes procesados, le damos un respiro al CPU
    contador_wdt++;
    if (contador_wdt % 500 == 0) {
        yield();
    }
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
void mantenerConexionMQTT() {
  if (mqttBroker == "" || !isOnline) return;
  
  // Si el cliente ya está inicializado, no hacemos nada 
  if (mqtt_client != NULL) return;

  addLog("Iniciando MQTT sobre WebSockets...");
  
  String brokerUrl = mqttBroker;

  // 1. Limpiamos cualquier prefijo guardado
  if (brokerUrl.startsWith("https://")) brokerUrl = brokerUrl.substring(8);
  else if (brokerUrl.startsWith("http://")) brokerUrl = brokerUrl.substring(7);
  if (brokerUrl.startsWith("wss://")) brokerUrl = brokerUrl.substring(6);
  else if (brokerUrl.startsWith("ws://")) brokerUrl = brokerUrl.substring(5);

  // 2. Le agregamos el path obligatorio (/mqtt)
  if (!brokerUrl.endsWith("/mqtt")) {
    if (brokerUrl.endsWith("/")) brokerUrl += "mqtt";
    else brokerUrl += "/mqtt";
  }

  // 3. Forzamos el protocolo Seguro WSS
  brokerUrl = "wss://" + brokerUrl;

  esp_mqtt_client_config_t mqtt_cfg = {};
  
  // Compatibilidad y asignación de certificados
  #if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
    mqtt_cfg.broker.address.uri = brokerUrl.c_str();
    mqtt_cfg.broker.verification.crt_bundle_attach = esp_crt_bundle_attach; // <--- Validación de cert en nuevas versiones
  #else
    mqtt_cfg.uri = brokerUrl.c_str();
    mqtt_cfg.crt_bundle_attach = esp_crt_bundle_attach; // <--- Validación de cert en versiones anteriores
  #endif

  mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
  esp_mqtt_client_register_event(mqtt_client, (esp_mqtt_event_id_t)ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
  esp_mqtt_client_start(mqtt_client);
}

// Registra el rostro de una persona nueva en el backend
bool registrarRostroEnBackend(String personaId) {
  if (!camaraIniciada || !isOnline) return false;

  // Si el cliente no existe, intentamos levantarlo
  if (mqtt_client == NULL) {
      mantenerConexionMQTT();
  }
  
  // Verificamos nuestra variable de estado
  if (!mqttConnected || mqtt_client == NULL) {
      addLog("Error: MQTT no conectado");
      return false;
  }

  addLog("Capturando rostro para registro...");
  String imgBase64 = capturarImagenBase64();
  
  if (imgBase64.length() == 0) return false;

  addLog("Transmitiendo imagen via MQTT...");

 esp_mqtt_client_publish(mqtt_client, "esp32/imagen/start", personaId.c_str(), 0, 0, 0);
  
  // 2. Fragmentación (Podemos usar chunks más grandes, ej. 500 bytes)
  int chunkSize = 500; 
  int longitudTotal = imgBase64.length();
  
  for (int i = 0; i < longitudTotal; i += chunkSize) {
    String chunk = imgBase64.substring(i, min(i + chunkSize, longitudTotal));
    esp_mqtt_client_publish(mqtt_client, "esp32/imagen/part", chunk.c_str(), 0, 0, 0);
    
    // ¡ESTO ES VITAL!
    // Obliga al ESP32 a esperar 30ms para que la antena WiFi tenga 
    // tiempo de enviar el paquete real antes de encolar el siguiente.
    delay(30); 
    yield(); 
  }
  
 // 3. Finalizamos la transmisión
  esp_mqtt_client_publish(mqtt_client, "esp32/imagen/end", "fin", 0, 0, 0);
  
  addLog("Transmision WS completa. Peso: " + String(longitudTotal) + " bytes");
  imgBase64 = String();
  
  return true; // Asumimos éxito al enviar. El backend procesará de forma asíncrona.
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
// ============================================================
// GUARDAR REGISTRO FINAL (POSTGRES + JSON + INICIAR FACIAL)
// ============================================================
// ============================================================
// GUARDAR REGISTRO FINAL (POSTGRES + JSON + INICIAR FACIAL)
// ============================================================
void completarRegistroPersona() {
  if (!isOnline) {
    addLog("Error: Sin conexión WiFi para registrar en BD. Abortando.");
    estadoActual = ESTADO_IDLE;
    nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = ""; slotRegistrando = -1;
    return;
  }

  addLog("Enviando datos al servidor...");
  HTTPClient http;
  http.begin(backendURL + "/api/personas");
  http.addHeader("Content-Type", "application/json");
  
  // Aumentamos a 10 segundos para darle tiempo al túnel de Cloudflare
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
    // FRENO DE MANO: Si el POST falla (Cod -1, 404, 500), detenemos todo.
    addLog("Error BD (Cod:" + String(httpCode) + "). Abortando captura facial.");
    estadoActual = ESTADO_IDLE; 
    
    // Si la huella se guardó en el sensor, deberíamos borrarla para no dejar basura
    finger.deleteModel(slotRegistrando);
    
    // Limpiamos variables
    nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = ""; slotRegistrando = -1;
    http.end();
    return; 
  }
  http.end();

  // Guardamos en el JSON local del SPIFFS solo si tuvimos éxito en el backend
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

  // === TRANSICIÓN AL REGISTRO FACIAL ===
  if (camaraIniciada) {
    addLog("Iniciando Bucle Facial. Mire a la cámara...");
    idParaRostro = idReal;   // Usamos el ID real de Postgres
    intentosFacial = 0;      
    estadoActual = ESTADO_REGISTRO_FACIAL; 
    tiempoUltimoEstado = millis();
  } else {
    addLog("Registro finalizado (Sin cámara)");
    estadoActual = ESTADO_IDLE;
    nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = ""; slotRegistrando = -1;
  }
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
  if (!server.hasArg("name") || !server.hasArg("rut")) { 
    server.send(400, "text/plain", "Faltan datos"); 
    return; 
  }
  
  int slot = encontrarSlotLibre();
  if (slot < 0) { server.send(500, "text/plain", "Sin slots"); return; }
  
  // Guardar datos en globales
  slotRegistrando = slot;
  nombreRegistrando = server.arg("name");
  rutRegistrando = server.arg("rut");
  emailRegistrando = server.arg("email");
  
  // ESTO ES LO ÚNICO QUE DEBE HACER: Cambiar el estado
  estadoActual = ESTADO_ESPERANDO_HUELLA_REGISTRO;
  tiempoUltimoEstado = millis();
  
  // AVISAR AL NAVEGADOR
  server.send(200, "text/plain", "OK: Ponga el dedo en el lector físico ahora...");
  
  // IMPORTANTE: BORRA la línea que decía completarRegistroPersona(); aquí.
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

  if (isOnline && mqtt_client == NULL) {
      mantenerConexionMQTT();
  }
  
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
        estadoActual       = ESTADO_ESPERANDO_SOLTAR_DEDO; // <--- CAMBIO AQUÍ
        tiempoUltimoEstado = millis();
      }
    }
    return;
  }

  // ===== NUEVO: Esperar a que quite el dedo =====
  if (estadoActual == ESTADO_ESPERANDO_SOLTAR_DEDO) {
    int p = finger.getImage();
    // Solo avanzamos si el sensor confirma que quitaste el dedo
    if (p == FINGERPRINT_NOFINGER) {
      addLog("Vuelva a colocar el mismo dedo...");
      estadoActual       = ESTADO_REGISTRO_SEGUNDA_HUELLA;
      tiempoUltimoEstado = millis();
    }
    // Si sigue detectando dedo (FINGERPRINT_OK), hace "return" y sigue esperando
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
// ===== Registro: Captura Facial Iterativa =====
  if (estadoActual == ESTADO_REGISTRO_FACIAL) {
    unsigned long ahoraLoop = millis();
    static unsigned long ultimoIntentoFoto = 0;
    
    // Le damos 4000ms (4 seg) al backend para analizar y responder por MQTT
    if (ahoraLoop - ultimoIntentoFoto > 4000) { 
      ultimoIntentoFoto = ahoraLoop;
      intentosFacial++;
      
      if (intentosFacial > 6) {
        addLog("Límite de intentos alcanzado. Registro sin rostro.");
        estadoActual = ESTADO_IDLE;
        return;
      }
      
      addLog("Tomando foto #" + String(intentosFacial) + " de 6...");
      
      // Disparamos la ráfaga MQTT (no bloquea el procesador)
      registrarRostroEnBackend(idParaRostro); 
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
