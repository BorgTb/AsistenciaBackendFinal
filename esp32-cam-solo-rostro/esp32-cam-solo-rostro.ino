// ============================================================
// ESP32-CAM Sistema de Asistencia - VERSION SOLO FACIAL
// Centinela (Facial) + Fetch Backend + Gestion Web
// Sin sensor de huellas AS608
// ============================================================

#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_wifi.h> // <-- VITAL: Para el manejo avanzado de energía del WiFi
#include "LittleFS.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include "esp_camera.h"
#include "mqtt_client.h"
#include "esp_crt_bundle.h" 
#include <mbedtls/md.h>

esp_mqtt_client_handle_t mqtt_client = NULL;
bool mqttConnected = false;

#define FLASH_PIN 4
#define GREEN_LED_PIN 2
#define PIR_PIN 12

// ===== Flash PWM (evita enceguecer a las personas) =====
#define FLASH_PWM_FREQ     5000  // 5 kHz: sin flicker visible
#define FLASH_PWM_RES      8     // 8 bits -> duty 0..255
#define FLASH_PWM_DUTY_50  128   // 50% de 255
#define FLASH_DUTY_LOW    64   // 25%
#define FLASH_DUTY_MED    128  // 50%
#define FLASH_DUTY_HIGH   191  // 75%
#define FLASH_DUTY_FULL   255  // 100%

unsigned long ultimoDisparoPIR = 0; // Para evitar que envíe 10 fotos en un segundo

WebServer server(80);

// ===== Configuracion AP =====
const char* apSSID   = "ESP32-ASISTENCIA";
const char* apPASS   = "Asistencia2026";

// ===== WiFi externo configurable =====
String savedSSID = "";
String savedPASS = "";
bool   isOnline  = false;
String deviceMAC  = "";
unsigned long lastHeartbeat = 0;

// ===== Backend y MQTT =====
String backendURL     = "https://sculpture-kong-filtering-essential.trycloudflare.com";
String mqttBroker     = "";
String pinEnrol       = ""; 
bool   estaEnrolado   = false;
String adminHash     = "";
String lastCapturedImageUrl = "";
bool   camaraIniciada = false;
bool   wifiEstabaConectado = false;

// ===== Timestamp y Control de Tiempos =====
unsigned long bootEpoch = 0;
unsigned long cooldownAsistencia = 0;             
const unsigned long COOLDOWN_TIEMPO = 8000;       

// ===== Escaneo automatico =====
unsigned long lastFaceCheck = 0;
const unsigned long FACE_CHECK_INTERVAL = 6000;
unsigned long bloqueoAsistenciaHasta = 0;
const unsigned long BLOQUEO_MENU_MS = 30000;      // <-- OPTIMIZADO: Bajado a 30s para no congelar la web
bool baselineMovimientoLista = false;
uint32_t firmaMovimientoAnterior = 0;
const uint32_t UMBRAL_MOVIMIENTO = 1800;
bool rostroRegistroExitoso = false;
String ultimoErrorRegistro = "";

#define FOTOS_REQUERIDAS 3
int fotosTomadas = 0;

// ===== Maquina de estados =====
enum EstadoSistema {
  ESTADO_IDLE = 0,
  ESTADO_REGISTRO_FACIAL = 3,
  ESTADO_PROCESANDO_ASISTENCIA = 5
};

EstadoSistema estadoActual    = ESTADO_IDLE;
String nombreRegistrando      = "";
String rutRegistrando         = "";
String emailRegistrando       = "";
unsigned long tiempoUltimoEstado = 0;
const unsigned long TIMEOUT_REGISTRO = 30000;

int intentosFacial = 0;
String idParaRostro = "";
String logBuffer = "";
bool modoEdicionRostro = false;
String personaEditandoId = "";
unsigned long ultimoLogDiagnosticoOffline = 0;
String wifiDisconnectReason = "";
int wifiDisconnectCount = 0;
unsigned long wifiUptimeStart = 0;

// ============================================================
// PROTOTIPOS
// ============================================================
JsonArray loadArray(const char* path, DynamicJsonDocument& doc);
void saveArray(const char* path, DynamicJsonDocument& doc);
String identificarPorRostro();
bool registrarRostroEnBackend(String personaId);
bool agregarFotoEnBackend(String personaId);
void completarRegistroPersona();
void sincronizarAsistencias();
void sincronizarPersonasDesdeBackend();
void sincronizarTurnosDesdeBackend();
void sincronizarAsignacionesDesdeBackend();
void sincronizarErpConfigDesdeBackend();
void enviarAsistenciaAErp(const String& personaId, const String& nombre, const String& tipo, const String& metodo);
void sincronizarPendientes();
String procesarAsistencia(String personaId, String metodo);
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
bool postAsistenciaEnBackend(const String& personaId, const String& nombre, const String& tipo, const String& metodo);
bool crearTurnoEnBackend(const String& nombre, const String& inicio, const String& fin, const String& dias, String& idBackend);
bool crearAsignacionEnBackend(const String& personaId, const String& turnoIdBackend, String& idBackend);
String obtenerTurnoBackendId(const String& turnoLocalId);
void sincronizarTurnosPendientes();
void sincronizarAsignacionesPendientes();
void enrolarDispositivo();
String buscarRutPersona(const String& personaId);

void handleWiFiConfig();
void handleRegisterUser();
void handleCreateTurn();
void handleAssignTurn();
void handleLimpiarDatos();
void handleSincronizar();
void handleFetchPersonas();
void handleSetBackend();
void handleEditarPersona();
void handleActualizarRostroPersona();
void handleAgregarFotosPersona();
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
          flashExito();
          fotosTomadas++;
          String fileName = doc["file_name"].as<String>();
          String urlBase = backendURL;
          if (urlBase.endsWith("/")) urlBase = urlBase.substring(0, urlBase.length() - 1);
          lastCapturedImageUrl = urlBase + "/static/previews/" + fileName;
          rostroRegistroExitoso = true;
          ultimoErrorRegistro = "";
          
          if (fotosTomadas >= FOTOS_REQUERIDAS) {
            addLog("Registro completo: " + String(fotosTomadas) + " fotos de referencia guardadas");
            estadoActual = ESTADO_IDLE;
            nombreRegistrando = "";
            rutRegistrando = "";
            emailRegistrando = "";
            idParaRostro = "";
            modoEdicionRostro = false;
            personaEditandoId = "";
            fotosTomadas = 0;
          } else {
            addLog("Foto de registro #" + String(fotosTomadas) + " aceptada. Esperando siguiente captura en " + String(FOTOS_REQUERIDAS - fotosTomadas) + " foto(s)...");
          }
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

void flashExito() {
  for (int i = 0; i < 2; i++) {
    digitalWrite(GREEN_LED_PIN, HIGH); delay(150);
    digitalWrite(GREEN_LED_PIN, LOW);  delay(150);
  }
}

void flashError() {
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
  if (ahora < bloqueoAsistenciaHasta) return "bloqueo_menu";

  if (!isOnline) {
    String motivo = "";
    if (!datosOfflineListos(motivo)) return motivo;
    return "habilitada";
  }
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
  config.frame_size    = FRAMESIZE_VGA;
  config.jpeg_quality  = 8;
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
  s->set_vflip(s, 0);
  s->set_hmirror(s, 1);
}

// Nota: identificarPorRostro() captura el frame raw directamente con calidad 10
// y lo envía como octet-stream sin Base64. Esta función queda disponible
// si en algún flujo puntual se necesita Base64 con calidad reducida (ej: preview web).
String capturarImagenBase64Identificacion() {
  sensor_t* s = esp_camera_sensor_get();
  s->set_quality(s, 10);
  String img = capturarImagenBase64();
  s->set_quality(s, 8);
  return img;
}


String capturarImagenBase64() {
  if (!camaraIniciada) return "";

  // 1. ILUMINACIÓN (Consumo alto: Flash ON al 50%)
  ledcWrite(FLASH_PIN, FLASH_DUTY_LOW);
  delay(200); // Damos tiempo al sensor OV2640 para ajustar brillo y enfoque

  // 2. CAPTURA DE HARDWARE (Guardamos la foto en la RAM)
  camera_fb_t* fb = esp_camera_fb_get();

  // 3. APAGADO INMEDIATO (Liberamos carga eléctrica de la fuente)
  ledcWrite(FLASH_PIN, 0);
  delay(150);
  if (!fb) {
    addLog("Error: Falla al capturar frame");
    return "";
  }

  // 4. PROCESAMIENTO A BASE64 (El Flash ya está apagado, el voltaje es estable)
  const char* b64chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  String encoded = "";
  encoded.reserve((fb->len * 4 / 3) + 2); 

  int i = 0;
  unsigned char buf3[3], buf4[4];
  int len = fb->len;
  uint8_t* data = fb->buf;

  // Codificación matemática (esto toma unos milisegundos, pero no consume amperaje extra)
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
  
  if (i > 0) {
    for (int j = i; j < 3; j++) buf3[j] = '\0';
    buf4[0] = (buf3[0] & 0xfc) >> 2;
    buf4[1] = ((buf3[0] & 0x03) << 4) + ((buf3[1] & 0xf0) >> 4);
    buf4[2] = ((buf3[1] & 0x0f) << 2) + ((buf3[2] & 0xc0) >> 6);
    buf4[3] = buf3[2] & 0x3f;
    for (int j = 0; j < i + 1; j++) encoded += b64chars[buf4[j]];
    while (i++ < 3) encoded += '='; 
  }
  
  // Liberamos la memoria del buffer de la cámara
  esp_camera_fb_return(fb);
  
  return encoded; // Retornamos el string gigante listo para enviar
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
  esp_wifi_set_ps(WIFI_PS_NONE);

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
  
  if (isOnline) {
    addLog("WiFi conectado");
    deviceMAC = WiFi.macAddress();
    deviceMAC.replace(":", "");
    addLog("MAC: " + deviceMAC);
    wifiEstabaConectado = true;
    enrolarDispositivo();
  } else {
    addLog("WiFi no disponible");
    wifiEstabaConectado = false;
    WiFi.disconnect();
  }
}

int reintentosWifi = 0;
unsigned long ultimoIntentoWifi = 0;

void verificarConexionWiFi() {
  if (savedSSID.length() == 0) return;

  if (WiFi.status() == WL_CONNECTED) {
    isOnline = true;
    reintentosWifi = 0;
    return;
  }

  if (!wifiEstabaConectado) return;

  isOnline = false;
  unsigned long ahora = millis();
  if (reintentosWifi > 0 && (ahora - ultimoIntentoWifi) < (reintentosWifi * 3000UL)) return;

  reintentosWifi++;
  ultimoIntentoWifi = ahora;
  addLog("WiFi perdido. Intento " + String(reintentosWifi) + "/5...");

  // Disconnect limpio antes de reconectar: evita el falso WL_WRONG_PASSWORD
  // que ocurre cuando el stack queda en estado de autenticacion inconsistente.
  WiFi.disconnect(false);
  delay(200);
  WiFi.begin(savedSSID.c_str(), savedPASS.c_str());

  int espera = 0;
  while (WiFi.status() != WL_CONNECTED && espera < 40) {
    delay(250);
    espera++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    isOnline = true;
    reintentosWifi = 0;
    addLog("WiFi reconectado");
    if (mqtt_client != NULL) {
      esp_mqtt_client_stop(mqtt_client);
      esp_mqtt_client_destroy(mqtt_client);
      mqtt_client = NULL;
      mqttConnected = false;
    }
  } else if (reintentosWifi >= 5) {
    addLog("5 intentos fallidos. Activando AP para reconfigurar...");
    WiFi.disconnect(true);
    delay(500);
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(apSSID, apPASS, 6, 0, 4);
    Serial.println("AP SSID: " + String(apSSID));
    Serial.println("AP PASS: " + String(apPASS));
    Serial.println("AP IP: " + WiFi.softAPIP().toString());
    Serial.println("AP Canal: " + String(WiFi.channel()));
    WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));
    addLog("AP activo: 192.168.4.1 - PASS=" + String(apPASS));
    // NO reseteamos wifiEstabaConectado para que el watchdog
    // pueda reintentar si el router vuelve a estar disponible.
    reintentosWifi = 0;
  }
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

  String lwtTopic = "esp32/lwt/" + deviceMAC;
  String lwtMsg = "{\"mac\":\"" + deviceMAC + "\",\"estado\":\"inactivo\"}";
  #if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
    mqtt_cfg.session.last_will.topic = lwtTopic.c_str();
    mqtt_cfg.session.last_will.msg = lwtMsg.c_str();
    mqtt_cfg.session.last_will.msg_len = lwtMsg.length();
    mqtt_cfg.session.last_will.qos = 0;
    mqtt_cfg.session.last_will.retain = 0;
  #else
    mqtt_cfg.lwt_topic = lwtTopic.c_str();
    mqtt_cfg.lwt_msg = lwtMsg.c_str();
    mqtt_cfg.lwt_msg_len = lwtMsg.length();
    mqtt_cfg.lwt_qos = 0;
    mqtt_cfg.lwt_retain = 0;
  #endif

  mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
  esp_mqtt_client_register_event(mqtt_client, (esp_mqtt_event_id_t)ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
  esp_mqtt_client_start(mqtt_client);
}

void enrolarDispositivo() {
  if (pinEnrol.length() == 0 || estaEnrolado) return;
  addLog("Enrolando dispositivo con PIN: " + pinEnrol);
  HTTPClient http;
  beginHttp(http, backendURL + "/api/dispositivos/enrolar");
  http.addHeader("Content-Type", "application/json");
  

  String macConDosPuntos = WiFi.macAddress();
  DynamicJsonDocument doc(256);
  doc["codigo"] = pinEnrol;
  doc["mac"] = macConDosPuntos;
  doc["ip"] = WiFi.localIP().toString();
  String payload;
  serializeJson(doc, payload);

  int code = http.POST(payload);
  if (code == 200) {
    addLog("Dispositivo enrolado correctamente");
    estaEnrolado = true;
    pinEnrol = "";
    String ssid = savedSSID, pass = savedPASS, backend = backendURL, mqtt = mqttBroker;
    saveConfig(ssid, pass, backend, mqtt, "");
  } else {
    addLog("Error enrolando: HTTP " + String(code) + " " + http.getString());
  }
  http.end();
}

void beginHttp(HTTPClient& http, const String& url) {
  http.begin(url);
  http.setTimeout(10000);
  if (deviceMAC.length() > 0) http.addHeader("X-Device-MAC", deviceMAC);
}

// ============================================================
// ADMIN LOCAL — SHA256 + Password
// ============================================================
String sha256(const String& input) {
  byte output[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);

  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (info == NULL) {
    addLog("[ADMIN] ERROR: mbedtls SHA256 no disponible");
    mbedtls_md_free(&ctx);
    return "";
  }

  int ret = mbedtls_md_setup(&ctx, info, 0);
  if (ret != 0) {
    addLog("[ADMIN] ERROR: mbedtls_md_setup fallo (codigo " + String(ret) + ")");
    mbedtls_md_free(&ctx);
    return "";
  }

  ret = mbedtls_md_starts(&ctx);
  if (ret != 0) {
    addLog("[ADMIN] ERROR: mbedtls_md_starts fallo (codigo " + String(ret) + ")");
    mbedtls_md_free(&ctx);
    return "";
  }

  ret = mbedtls_md_update(&ctx, (const unsigned char*)input.c_str(), input.length());
  if (ret != 0) {
    addLog("[ADMIN] ERROR: mbedtls_md_update fallo (codigo " + String(ret) + ")");
    mbedtls_md_free(&ctx);
    return "";
  }

  ret = mbedtls_md_finish(&ctx, output);
  if (ret != 0) {
    addLog("[ADMIN] ERROR: mbedtls_md_finish fallo (codigo " + String(ret) + ")");
    memset(output, 0, 32);
    mbedtls_md_free(&ctx);
    return "";
  }
  mbedtls_md_free(&ctx);

  char hex[65];
  for (int i = 0; i < 32; i++) {
    snprintf(hex + (i * 2), 3, "%02x", output[i]);
  }
  hex[64] = '\0';
  return String(hex);
}

void cargarAdminHash() {
  if (!LittleFS.exists("/admin.json")) {
    addLog("[ADMIN] /admin.json no existe, sin proteccion");
    return;
  }
  File file = LittleFS.open("/admin.json", "r");
  if (file) {
    DynamicJsonDocument doc(128);
    DeserializationError err = deserializeJson(doc, file);
    if (err) {
      addLog("[ADMIN] ERROR parseando /admin.json: " + String(err.c_str()));
      file.close();
      return;
    }
    if (doc.containsKey("admin_hash")) {
      adminHash = doc["admin_hash"].as<String>();
      addLog("[ADMIN] Hash cargado (" + String(adminHash.length()) + " chars)");
    } else {
      addLog("[ADMIN] /admin.json sin campo admin_hash");
    }
    file.close();
  }
}

void saveAdminHash() {
  DynamicJsonDocument doc(128);
  doc["admin_hash"] = adminHash;
  File file = LittleFS.open("/admin.json", "w");
  if (file) {
    serializeJson(doc, file);
    file.close();
    addLog("[ADMIN] Hash guardado en /admin.json");
  } else {
    addLog("[ADMIN] ERROR: no se pudo escribir /admin.json");
  }
}

bool verificarPassword(const String& password) {
  if (adminHash.length() == 0) return true;
  String hash = sha256(password);
  if (hash.length() == 0) {
    addLog("[ADMIN] ERROR: sha256 fallo durante verificacion - acceso denegado");
    return false;
  }
  bool ok = (hash == adminHash);
  if (!ok) addLog("[ADMIN] Password incorrecto (hash_len=" + String(hash.length()) + " admin_len=" + String(adminHash.length()) + ")");
  return ok;
}

bool requiereAdmin(WebServer& srv) {
  if (adminHash.length() == 0) return true;
  addLog("[ADMIN] Verificando acceso a " + srv.uri() + " (hash_len=" + String(adminHash.length()) + ")");
  if (!srv.hasArg("admin_password")) {
    addLog("[ADMIN] Falta admin_password en request");
    srv.send(401, "text/plain", "Se requiere contrasena de administrador");
    return false;
  }
  String pw = srv.arg("admin_password");
  addLog("[ADMIN] Password recibido (" + String(pw.length()) + " chars)");
  if (!verificarPassword(pw)) {
    addLog("[ADMIN] Password INCORRECTO");
    srv.send(401, "text/plain", "Contrasena incorrecta");
    return false;
  }
  addLog("[ADMIN] Acceso concedido a " + srv.uri());
  return true;
}

void sincronizarPersonasDesdeBackend() {
  if (!isOnline || WiFi.status() != WL_CONNECTED) {
    addLog("Sin WiFi: No se puede fetchear personas.");
    return;
  }
  addLog("Fetcheando lista de personas desde Backend...");
  HTTPClient http;
  beginHttp(http, backendURL + "/api/personas");

  int httpCode = http.GET();
  if (httpCode == 200) {
    DynamicJsonDocument doc(8192); 
    DeserializationError error = deserializeJson(doc, http.getStream());

    if (!error) {
      File file = LittleFS.open("/personas.json", "w");
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

  // Calidad reducida para identificación: más rápido de transmitir y procesar
  sensor_t* s = esp_camera_sensor_get();
  s->set_quality(s, 10);

  // Flash breve para iluminar el rostro
  ledcWrite(FLASH_PIN, FLASH_DUTY_LOW);
  delay(150);
  camera_fb_t* fb = esp_camera_fb_get();
  ledcWrite(FLASH_PIN, 0);

  // Restaurar calidad original para registro
  s->set_quality(s, 8);

  if (!fb) {
    addLog("Error: No se pudo capturar frame para identificacion");
    return "";
  }

  HTTPClient http;
  beginHttp(http, backendURL + "/api/facial/identificar");
  http.addHeader("Content-Type", "application/octet-stream");
  http.setTimeout(10000);

  // Enviar JPEG crudo directamente, sin Base64 (33% menos datos)
  int httpCode = http.POST(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  String personaId = "";
  if (httpCode == 200) {
    DynamicJsonDocument doc(256);
    deserializeJson(doc, http.getString());
    if (doc.containsKey("persona_id")) {
      personaId = doc["persona_id"].as<String>();
    }
  } else if (httpCode != 404) {
    // 404 es "rostro no reconocido", es esperado — solo logueamos errores reales
    addLog("Identificacion HTTP error: " + String(httpCode));
  }
  http.end();
  return personaId;
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

  if (postAsistenciaEnBackend(personaId, nombre, tipo, metodo)) {
    a["sincronizado"] = true;
  }
  
  saveArray("/asistencias.json", docA);

  if (isOnline) enviarAsistenciaAErp(personaId, nombre, tipo, metodo);

  String tipoMayus = tipo;
  tipoMayus.toUpperCase();
  return tipoMayus + " OK: " + nombre + " (" + metodo + ")";
}

bool postAsistenciaEnBackend(const String& personaId, const String& nombre, const String& tipo, const String& metodo) {
  if (!isOnline || WiFi.status() != WL_CONNECTED) return false;
  if (personaId.startsWith("local-")) return false;

  HTTPClient http;
  beginHttp(http, backendURL + "/api/asistencias");
  http.addHeader("Content-Type", "application/json");
  

  DynamicJsonDocument payloadDoc(512);
  payloadDoc["persona_id"] = personaId;
  payloadDoc["nombre"] = nombre;
  payloadDoc["tipo"] = tipo;
  payloadDoc["metodo"] = metodo;
  payloadDoc["origen"] = "dispositivo";
  payloadDoc["sincronizado"] = true;
  String payload;
  serializeJson(payloadDoc, payload);

  int code = http.POST(payload);
  if (code != 200 && code != 201) {
    addLog("Asistencia local guardada, backend pendiente. Codigo: " + String(code));
    http.end();
    return false;
  }

  http.end();
  return true;
}

bool crearTurnoEnBackend(const String& nombre, const String& inicio, const String& fin, const String& dias, String& idBackend) {
  idBackend = "";
  if (!isOnline || WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  beginHttp(http, backendURL + "/api/turnos");
  http.addHeader("Content-Type", "application/json");
  

  DynamicJsonDocument payloadDoc(512);
  payloadDoc["nombre"] = nombre;
  payloadDoc["inicio"] = inicio;
  payloadDoc["fin"] = fin;
  payloadDoc["dias"] = dias;
  String payload;
  serializeJson(payloadDoc, payload);

  int code = http.POST(payload);
  if (code != 200 && code != 201) {
    addLog("Turno local guardado, backend pendiente. Codigo: " + String(code));
    http.end();
    return false;
  }

  DynamicJsonDocument respDoc(256);
  DeserializationError err = deserializeJson(respDoc, http.getString());
  http.end();
  if (!err && respDoc.containsKey("id")) {
    idBackend = respDoc["id"].as<String>();
    return idBackend.length() > 0;
  }

  addLog("Turno creado en backend sin ID util.");
  return false;
}

bool crearAsignacionEnBackend(const String& personaId, const String& turnoIdBackend, String& idBackend) {
  idBackend = "";
  if (!isOnline || WiFi.status() != WL_CONNECTED) return false;
  if (personaId.startsWith("local-") || turnoIdBackend.length() == 0) return false;

  HTTPClient http;
  beginHttp(http, backendURL + "/api/asignaciones");
  http.addHeader("Content-Type", "application/json");
  

  DynamicJsonDocument payloadDoc(512);
  payloadDoc["persona_id"] = personaId;
  payloadDoc["turno_id"] = turnoIdBackend;
  String payload;
  serializeJson(payloadDoc, payload);

  int code = http.POST(payload);
  if (code != 200 && code != 201) {
    addLog("Asignacion local guardada, backend pendiente. Codigo: " + String(code));
    http.end();
    return false;
  }

  DynamicJsonDocument respDoc(256);
  DeserializationError err = deserializeJson(respDoc, http.getString());
  http.end();
  if (!err && respDoc.containsKey("id")) {
    idBackend = respDoc["id"].as<String>();
  }
  return true;
}

String obtenerTurnoBackendId(const String& turnoLocalId) {
  DynamicJsonDocument doc(4096);
  JsonArray turnos = loadArray("/turnos.json", doc);
  for (JsonObject t : turnos) {
    if (t["id"].as<String>() == turnoLocalId) {
      if (t.containsKey("backend_id") && t["backend_id"].as<String>().length() > 0) {
        return t["backend_id"].as<String>();
      }
      String id = t["id"].as<String>();
      if (!id.startsWith("local-")) return id;
      return "";
    }
  }
  return "";
}

// ============================================================
// REGISTRO DE USUARIOS
// ============================================================
void completarRegistroPersona() {
  ultimoErrorRegistro = "";
  rostroRegistroExitoso = false;

  String idReal = "";
  bool personaCreadaEnBackend = false;

  if (isOnline && WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
  beginHttp(http, backendURL + "/api/personas");
    http.addHeader("Content-Type", "application/json");
    

    DynamicJsonDocument bodyDoc(512);
    bodyDoc["nombre"] = nombreRegistrando;
    bodyDoc["rut"] = rutRegistrando;
    bodyDoc["email"] = emailRegistrando;
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
    idReal = "local-" + String(getTimestamp());
  }

  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);
  JsonObject p = personas.createNestedObject();
  p["id"]             = idReal;
  p["nombre"]         = nombreRegistrando;
  p["rut"]            = rutRegistrando;
  p["email"]          = emailRegistrando;
  p["fecha_registro"] = getTimestamp();
  p["sincronizado"]   = personaCreadaEnBackend;
  saveArray("/personas.json", doc);
  
  if (personaCreadaEnBackend && camaraIniciada) {
    addLog("Mire a la cámara para la foto...");
    idParaRostro = idReal;   
    intentosFacial = 0;
    fotosTomadas = 0;
    actualizarBloqueoAsistencia(60000); // 1 minuto de bloqueo para la foto es suficiente
    estadoActual = ESTADO_REGISTRO_FACIAL;
    tiempoUltimoEstado = millis();
  } else {
    if (!personaCreadaEnBackend) {
      addLog("Registro local completado (pendiente de sincronizacion con backend).");
    }
    rostroRegistroExitoso = true;
    estadoActual = ESTADO_IDLE;
    nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = "";
  }
}

bool registrarRostroEnBackend(String personaId) {
  if (!camaraIniciada || !isOnline || !mqttConnected || mqtt_client == NULL) return false;

  String imgBase64 = capturarImagenBase64();
  if (imgBase64.length() == 0) return false;

  // Un único mensaje JSON — sin fragmentación, sin delays artificiales
  String payload = "{\"persona_id\":\"" + personaId + "\",\"imagen\":\"" + imgBase64 + "\"}";
  addLog("Enviando rostro MQTT: " + String(payload.length()) + " bytes para ID " + personaId);

  int ret = esp_mqtt_client_publish(
    mqtt_client,
    "esp32/imagen/registrar",
    payload.c_str(),
    payload.length(),
    1,  // QoS 1: el broker confirma la entrega
    0
  );

  if (ret < 0) {
    addLog("Error publicando MQTT (ret=" + String(ret) + ")");
    return false;
  }
  return true;
}

bool agregarFotoEnBackend(String personaId) {
  if (!camaraIniciada || !isOnline || WiFi.status() != WL_CONNECTED) return false;

  String imgBase64 = capturarImagenBase64();
  if (imgBase64.length() == 0) return false;

  HTTPClient http;
  beginHttp(http, backendURL + "/api/facial/agregar-foto");
  http.addHeader("Content-Type", "application/json");

  String payload = "{\"persona_id\":\"" + personaId + "\",\"imagen\":\"" + imgBase64 + "\"}";
  int code = http.POST(payload);
  http.end();

  if (code == 200) {
    addLog("Foto adicional guardada en backend para ID " + personaId);
    return true;
  }
  addLog("Error agregando foto extra: HTTP " + String(code));
  return false;
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
  beginHttp(http, backendURL + "/api/asistencias/sync");
  http.addHeader("Content-Type", "application/json");
  
  int code = http.POST(body);
  http.end();

  if (code == 200) {
    for (JsonObject a : asist) a["sincronizado"] = true;
    saveArray("/asistencias.json", doc);
    addLog("Sincronizacion completada");
  }
}

void sincronizarTurnosPendientes() {
  if (!isOnline || WiFi.status() != WL_CONNECTED) return;

  DynamicJsonDocument doc(8192);
  JsonArray turnos = loadArray("/turnos.json", doc);
  bool huboCambios = false;

  for (JsonObject t : turnos) {
    bool sincronizado = t.containsKey("sincronizado") ? t["sincronizado"].as<bool>() : false;
    String backendId = t.containsKey("backend_id") ? t["backend_id"].as<String>() : "";
    if (sincronizado && backendId.length() > 0) continue;

    String nuevoId = "";
    if (crearTurnoEnBackend(
      t["nombre"].as<String>(),
      t["inicio"].as<String>(),
      t["fin"].as<String>(),
      t["dias"].as<String>(),
      nuevoId
    )) {
      if (nuevoId.length() > 0) {
        t["backend_id"] = nuevoId;
        t["sincronizado"] = true;
        huboCambios = true;
      }
    }
  }

  if (huboCambios) {
    saveArray("/turnos.json", doc);
    addLog("Turnos pendientes sincronizados");
  }
}

void sincronizarAsignacionesPendientes() {
  if (!isOnline || WiFi.status() != WL_CONNECTED) return;

  DynamicJsonDocument doc(8192);
  JsonArray asignaciones = loadArray("/asignaciones.json", doc);
  bool huboCambios = false;

  for (JsonObject a : asignaciones) {
    bool sincronizado = a.containsKey("sincronizado") ? a["sincronizado"].as<bool>() : false;
    if (sincronizado) continue;

    String personaId = a["persona_id"].as<String>();
    if (personaId.startsWith("local-")) continue;

    String turnoBackendId = obtenerTurnoBackendId(a["turno_id"].as<String>());
    if (turnoBackendId.length() == 0) continue;

    String asigBackendId = "";
    if (crearAsignacionEnBackend(personaId, turnoBackendId, asigBackendId)) {
      a["sincronizado"] = true;
      if (asigBackendId.length() > 0) a["backend_id"] = asigBackendId;
      huboCambios = true;
    }
  }

  if (huboCambios) {
    saveArray("/asignaciones.json", doc);
    addLog("Asignaciones pendientes sincronizadas");
  }
}

void sincronizarTurnosDesdeBackend() {
  if (!isOnline || WiFi.status() != WL_CONNECTED) return;

  DynamicJsonDocument docLocal(8192);
  JsonArray turnosLocales = loadArray("/turnos.json", docLocal);
  for (JsonObject t : turnosLocales) {
    bool sincronizado = t.containsKey("sincronizado") ? t["sincronizado"].as<bool>() : false;
    if (!sincronizado) {
      addLog("Turnos locales pendientes detectados, se omite sobreescritura desde backend");
      return;
    }
  }

  HTTPClient http;
  beginHttp(http, backendURL + "/api/turnos");
  
  int code = http.GET();
  if (code != 200) {
    addLog("Error HTTP al fetchear turnos: " + String(code));
    http.end();
    return;
  }

  DynamicJsonDocument doc(8192);
  DeserializationError error = deserializeJson(doc, http.getStream());
  http.end();
  if (error || !doc.is<JsonArray>()) {
    addLog("Error parseando JSON de turnos.");
    return;
  }

  JsonArray arr = doc.as<JsonArray>();
  for (JsonObject t : arr) {
    String id = t["id"].as<String>();
    t["backend_id"] = id;
    t["sincronizado"] = true;
  }
  saveArray("/turnos.json", doc);
}

void sincronizarAsignacionesDesdeBackend() {
  if (!isOnline || WiFi.status() != WL_CONNECTED) return;

  DynamicJsonDocument docLocal(8192);
  JsonArray asignLocales = loadArray("/asignaciones.json", docLocal);
  for (JsonObject a : asignLocales) {
    bool sincronizado = a.containsKey("sincronizado") ? a["sincronizado"].as<bool>() : false;
    if (!sincronizado) {
      addLog("Asignaciones locales pendientes detectadas, se omite sobreescritura desde backend");
      return;
    }
  }

  HTTPClient http;
  beginHttp(http, backendURL + "/api/asignaciones");
  
  int code = http.GET();
  if (code != 200) {
    addLog("Error HTTP al fetchear asignaciones: " + String(code));
    http.end();
    return;
  }

  DynamicJsonDocument doc(12288);
  DeserializationError error = deserializeJson(doc, http.getStream());
  http.end();
  if (error || !doc.is<JsonArray>()) {
    addLog("Error parseando JSON de asignaciones.");
    return;
  }

  JsonArray arr = doc.as<JsonArray>();
  for (JsonObject a : arr) {
    a["backend_id"] = a["id"].as<String>();
    a["sincronizado"] = true;
  }
  saveArray("/asignaciones.json", doc);
}

void sincronizarErpConfigDesdeBackend() {
  if (!isOnline || WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  beginHttp(http, backendURL + "/api/dispositivos/erp-config");
  int code = http.GET();
  if (code == 200) {
    DynamicJsonDocument doc(4096);
    DeserializationError error = deserializeJson(doc, http.getStream());
    if (!error) {
      File file = LittleFS.open("/erp-config.json", "w");
      serializeJson(doc, file);
      file.close();
    }
  }
  http.end();
}

void verificarPasswordPendiente() {
  if (!isOnline || WiFi.status() != WL_CONNECTED || deviceMAC.length() == 0) return;

  HTTPClient http;
  beginHttp(http, backendURL + "/api/dispositivos/check-password");
  int code = http.GET();
  if (code == 200) {
    DynamicJsonDocument doc(192);
    DeserializationError error = deserializeJson(doc, http.getStream());
    if (!error && doc["pendiente"] == true) {
      String newPassword = doc["password"].as<String>();
      if (newPassword.length() > 0) {
        adminHash = sha256(newPassword);
        saveAdminHash();
        addLog("Password actualizada desde backend");

        HTTPClient http2;
        beginHttp(http2, backendURL + "/api/dispositivos/confirmar-password");
        http2.POST("");
        http2.end();
      }
    }
  }
  http.end();
}

void enviarAsistenciaAErp(const String& personaId, const String& nombre, const String& tipo, const String& metodo) {
  if (!LittleFS.exists("/erp-config.json")) return;

  DynamicJsonDocument doc(4096);
  File file = LittleFS.open("/erp-config.json", "r");
  DeserializationError error = deserializeJson(doc, file);
  file.close();
  if (error || !doc.is<JsonArray>()) return;

  JsonArray erps = doc.as<JsonArray>();
  for (JsonObject erp : erps) {
    if (!erp["activo"].as<bool>() || !erp["envioAuto"].as<bool>()) continue;

    String webhookUrl = erp["webhookUrl"].as<String>();
    if (webhookUrl.length() == 0) continue;

    String fieldMap = erp["fieldMap"].as<String>();
    DynamicJsonDocument payloadDoc(512);

    if (fieldMap != "{}" && fieldMap.length() > 2) {
      DynamicJsonDocument fmDoc(256);
      deserializeJson(fmDoc, fieldMap);
      JsonObject fm = fmDoc.as<JsonObject>();
      for (JsonPair kv : fm) {
        String key = kv.key().c_str();
        String val = kv.value().as<String>();
        if (key == "rut") payloadDoc[val] = buscarRutPersona(personaId);
        else if (key == "persona_id") payloadDoc[val] = personaId;
        else if (key == "nombre") payloadDoc[val] = nombre;
        else if (key == "tipo") payloadDoc[val] = tipo;
        else if (key == "metodo") payloadDoc[val] = metodo;
        else if (key == "fecha_hora") payloadDoc[val] = String(getTimestamp());
        else payloadDoc[key] = val;
      }
    } else {
      payloadDoc["persona_id"] = personaId;
      payloadDoc["nombre"] = nombre;
      payloadDoc["tipo"] = tipo;
      payloadDoc["metodo"] = metodo;
      payloadDoc["fecha_hora"] = String(getTimestamp());
    }

    String headersStr = erp["headers"].as<String>();
    HTTPClient http;
    http.begin(webhookUrl);
    http.addHeader("Content-Type", "application/json");
    if (headersStr != "{}" && headersStr.length() > 2) {
      DynamicJsonDocument hDoc(256);
      deserializeJson(hDoc, headersStr);
      for (JsonPair kv : hDoc.as<JsonObject>()) {
        String val = kv.value().as<String>();
        val.replace("TOKEN", ""); val.replace("API_KEY", ""); val.replace("SAP_KEY", "");
        if (val.length() > 0) http.addHeader(kv.key().c_str(), val);
      }
    }
    http.setTimeout(8000);

    String payloadStr;
    serializeJson(payloadDoc, payloadStr);
    int respCode = http.POST(payloadStr);
    addLog("ERP push: " + webhookUrl + " -> HTTP " + String(respCode));
    http.end();
    yield();
  }
}

String buscarRutPersona(const String& personaId) {
  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);
  for (JsonObject p : personas) {
    if (p["id"].as<String>() == personaId) return p["rut"].as<String>();
  }
  return "";
}

void sincronizarPendientes() {
  sincronizarTurnosPendientes();
  sincronizarAsignacionesPendientes();
  sincronizarAsistencias();
}

// ============================================================
// LittleFS — JSON
// ============================================================
JsonArray loadArray(const char* path, DynamicJsonDocument& doc) {
  if (!LittleFS.exists(path)) { doc.set(JsonArray()); return doc.as<JsonArray>(); }
  File file = LittleFS.open(path, "r");
  if (!file) { doc.set(JsonArray()); return doc.as<JsonArray>(); }
  DeserializationError err = deserializeJson(doc, file);
  file.close();
  if (err || !doc.is<JsonArray>()) doc.set(JsonArray());
  return doc.as<JsonArray>();
}

void saveArray(const char* path, DynamicJsonDocument& doc) {
  File file = LittleFS.open(path, "w");
  serializeJson(doc, file);
  file.close();
}

void initLittleFS() {
  if (!LittleFS.begin(true)) return;
  const char* files[] = { "/personas.json", "/turnos.json", "/asignaciones.json", "/asistencias.json", "/wifi.json", "/admin.json" };
  for (auto f : files) {
    if (!LittleFS.exists(f)) {
      File file = LittleFS.open(f, "w");
      if (String(f) == "/wifi.json") file.println("{\"ssid\":\"\",\"pass\":\"\",\"backend\":\"http://172.20.10.3:5000\",\"mqtt\":\"\",\"pin\":\"\"}");
      else if (String(f) == "/admin.json") file.println("{}");
      else file.println("[]");
      file.close();
    }
  }
}

void loadWiFiConfig() {
  File file = LittleFS.open("/wifi.json", "r");
  if (file) {
    DynamicJsonDocument doc(512);
    deserializeJson(doc, file);
    if (doc.containsKey("ssid")) savedSSID = doc["ssid"].as<String>();
    if (doc.containsKey("pass")) savedPASS = doc["pass"].as<String>();
    if (doc.containsKey("backend")) backendURL = doc["backend"].as<String>();
    if (doc.containsKey("mqtt")) mqttBroker = doc["mqtt"].as<String>();
    if (doc.containsKey("pin")) pinEnrol = doc["pin"].as<String>();
    file.close();
  }
  cargarAdminHash();
}

void saveConfig(String ssid, String pass, String backend, String mqtt, String pin) {
  DynamicJsonDocument doc(512);
  doc["ssid"] = ssid; doc["pass"] = pass; doc["backend"] = backend; doc["mqtt"] = mqtt; doc["pin"] = pin;
  File file = LittleFS.open("/wifi.json", "w");
  serializeJson(doc, file); file.close();
  savedSSID = ssid; savedPASS = pass; backendURL = backend; mqttBroker = mqtt; pinEnrol = pin;
}

void servirArchivo(const char* path, const char* tipo) {
  bool existe = LittleFS.exists(path);
  addLog(String("[FILE] servirArchivo ") + path + " existe=" + (existe ? "SI" : "NO"));
  if (!existe) { server.send(404, "text/plain", "Archivo no encontrado"); return; }
  File f = LittleFS.open(path, "r");
  server.streamFile(f, tipo);
  f.close();
  addLog(String("[FILE] servirArchivo ") + path + " -> 200 (" + tipo + ")");
  yield(); 
}

// ============================================================
// HANDLERS WEB
// ============================================================
void handleWiFiConfig() {
  actualizarBloqueoAsistencia(60000);
  String ssid    = server.hasArg("ssid")    && server.arg("ssid").length()    > 0 ? server.arg("ssid")    : savedSSID;
  String pass    = server.hasArg("pass")    && server.arg("pass").length()    > 0 ? server.arg("pass")    : savedPASS;
  String backend = server.hasArg("backend") && server.arg("backend").length() > 0 ? server.arg("backend") : backendURL;
  String mqtt    = server.hasArg("mqtt")    && server.arg("mqtt").length()    > 0 ? server.arg("mqtt")    : mqttBroker;
  String pin     = server.hasArg("pin")     && server.arg("pin").length()     > 0 ? server.arg("pin")     : pinEnrol;

  if (server.hasArg("admin_password_new") && server.arg("admin_password_new").length() > 0) {
    if (adminHash.length() > 0) {
      if (!server.hasArg("admin_password_old") || !verificarPassword(server.arg("admin_password_old"))) {
        server.send(401, "text/plain", "Contrasena actual incorrecta");
        return;
      }
    }
    adminHash = sha256(server.arg("admin_password_new"));
    saveAdminHash();
  }

  saveConfig(ssid, pass, backend, mqtt, pin);
  server.send(200, "text/plain", "Guardado. Reiniciando...");
  delay(1500); ESP.restart();
}

void handleRegisterUser() {
  if (!requiereAdmin(server)) return;
  if (!server.hasArg("name") || !server.hasArg("rut")) { server.send(400, "text/plain", "Faltan datos"); return; }
  ultimoErrorRegistro = "";
  rostroRegistroExitoso = false;
  actualizarBloqueoAsistencia(60000);
  nombreRegistrando = server.arg("name"); rutRegistrando = server.arg("rut"); emailRegistrando = server.arg("email");
  completarRegistroPersona();
  server.send(200, "text/plain", "OK: Mire a la camara...");
}

void handleCreateTurn() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
  if (!server.hasArg("nombre") || !server.hasArg("inicio") || !server.hasArg("fin") || !server.hasArg("dias")) {
    server.send(400, "text/plain", "Datos incompletos");
    return;
  }
  DynamicJsonDocument doc(4096);
  JsonArray turnos = loadArray("/turnos.json", doc);
  JsonObject t = turnos.createNestedObject();

  String nombre = server.arg("nombre");
  String inicio = server.arg("inicio");
  String fin = server.arg("fin");
  String dias = server.arg("dias");
  String localId = "local-" + String(getTimestamp()) + "-" + String(turnos.size() + 1);
  String backendId = "";
  bool synced = crearTurnoEnBackend(nombre, inicio, fin, dias, backendId);

  t["id"] = synced && backendId.length() > 0 ? backendId : localId;
  t["backend_id"] = synced && backendId.length() > 0 ? backendId : "";
  t["nombre"] = nombre;
  t["inicio"] = inicio;
  t["fin"] = fin;
  t["dias"] = dias;
  t["sincronizado"] = synced;

  saveArray("/turnos.json", doc);
  server.send(200, "text/plain", synced ? "Turno creado y sincronizado" : "Turno creado local (pendiente sync)");
}

void handleAssignTurn() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
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

  String backendAsignacionId = "";
  bool synced = false;
  String turnoBackendId = obtenerTurnoBackendId(turnoId);
  if (turnoBackendId.length() == 0 && isOnline) {
    sincronizarTurnosPendientes();
    turnoBackendId = obtenerTurnoBackendId(turnoId);
  }
  if (turnoBackendId.length() > 0) {
    synced = crearAsignacionEnBackend(personaId, turnoBackendId, backendAsignacionId);
  }

  JsonObject a = asignaciones.createNestedObject();
  a["persona_id"]       = personaId;
  a["turno_id"]         = turnoId;
  a["fecha_asignacion"] = getTimestamp();
  a["sincronizado"]     = synced;
  if (backendAsignacionId.length() > 0) a["backend_id"] = backendAsignacionId;
  saveArray("/asignaciones.json", doc);
  server.send(200, "text/plain", synced ? "Turno asignado y sincronizado" : "Turno asignado local (pendiente sync)");
}

void handleLimpiarDatos() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
  if (!server.hasArg("codigo") || server.arg("codigo") != "1234") {
    server.send(403, "text/plain", "Codigo incorrecto");
    return;
  }
  const char* files[] = {"/personas.json", "/turnos.json", "/asignaciones.json", "/asistencias.json"};
  for (auto f : files) {
    File file = LittleFS.open(f, "w");
    file.println("[]");
    file.close();
  }
  addLog("Sistema limpiado");
  server.send(200, "text/plain", "Sistema limpiado correctamente");
}

void handleSincronizar() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
  if (!isOnline) { server.send(503, "text/plain", "Sin conexion"); return; }
  sincronizarPendientes();
  sincronizarPersonasDesdeBackend();
  sincronizarTurnosDesdeBackend();
  sincronizarAsignacionesDesdeBackend();
  server.send(200, "text/plain", "Sincronizacion ejecutada");
}

void handleFetchPersonas() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
  if (!isOnline) { server.send(503, "text/plain", "Sin conexion WiFi"); return; }
  sincronizarPersonasDesdeBackend();
  server.send(200, "text/plain", "Personas obtenidas. Revisa los logs.");
}

void handleSetBackend() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
  if (!server.hasArg("url")) { server.send(400, "text/plain", "Falta url"); return; }
  backendURL = server.arg("url");
  addLog("Backend actualizado: " + backendURL);
  server.send(200, "text/plain", "Backend: " + backendURL);
}

void handleEditarPersona() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia(60000);
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
  beginHttp(http, backendURL + "/api/personas/" + id);
    http.addHeader("Content-Type", "application/json");
    

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

void handleActualizarRostroPersona() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia(60000);
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
  fotosTomadas = 0;
  rostroRegistroExitoso = false;
  ultimoErrorRegistro = "";
  estadoActual = ESTADO_REGISTRO_FACIAL;
  tiempoUltimoEstado = millis();

  server.send(200, "text/plain", "Mire a la camara para actualizar rostro");
}

void handleAgregarFotosPersona() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia(60000);
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
    server.send(503, "text/plain", "Sin conexion para agregar fotos");
    return;
  }

  modoEdicionRostro = false;
  personaEditandoId = "";
  idParaRostro = id;
  intentosFacial = 0;
  fotosTomadas = 1;  // Ya existe al menos una foto, saltamos a fotos adicionales
  rostroRegistroExitoso = false;
  ultimoErrorRegistro = "";
  estadoActual = ESTADO_REGISTRO_FACIAL;
  tiempoUltimoEstado = millis();

  server.send(200, "text/plain", "Mire a la camara para capturar " + String(FOTOS_REQUERIDAS - 1) + " foto(s) adicional(es)");
}

void handleBorrarPersona() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
  if (!server.hasArg("id")) { server.send(400, "text/plain", "Falta ID"); return; }
  String id = server.arg("id");

  if (isOnline && WiFi.status() == WL_CONNECTED && !id.startsWith("local-")) {
    HTTPClient http;
  beginHttp(http, backendURL + "/api/personas/" + id);
    int httpCode = http.sendRequest("DELETE");
    if (httpCode == 200) {
      addLog("Persona borrada en BD remota OK");
    } else {
      addLog("Error borrando persona remota (Cod: " + String(httpCode) + ")");
    }
    http.end();
  }

  DynamicJsonDocument doc(2048);
  JsonArray arr = loadArray("/personas.json", doc);
  for (JsonArray::iterator it = arr.begin(); it != arr.end(); ++it) {
    if ((*it)["id"].as<String>() == id) {
      arr.remove(it);
      saveArray("/personas.json", doc);
      server.send(200, "text/plain", "Persona eliminada");
      return;
    }
  }
  server.send(404, "text/plain", "Persona no encontrada localmente");
}

void handleBorrarTurno() {
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
  if (!server.hasArg("id")) { server.send(400, "text/plain", "Falta ID"); return; }
  String id = server.arg("id");

  if (isOnline && WiFi.status() == WL_CONNECTED && !id.startsWith("local-")) {
    HTTPClient http;
  beginHttp(http, backendURL + "/api/turnos/" + id);
    int httpCode = http.sendRequest("DELETE");
    if (httpCode == 200) addLog("Turno borrado en BD remota OK");
    else addLog("Error borrando turno remoto (Cod: " + String(httpCode) + ")");
    http.end();
  }

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
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia();
  if (!server.hasArg("persona") || !server.hasArg("turno")) { server.send(400, "text/plain", "Faltan datos"); return; }
  String persona = server.arg("persona");
  String turno = server.arg("turno");
  
  DynamicJsonDocument doc(1024);
  JsonArray arr = loadArray("/asignaciones.json", doc);
  
  for (JsonArray::iterator it = arr.begin(); it != arr.end(); ++it) {
    if ((*it)["persona_id"].as<String>() == persona && (*it)["turno_id"].as<String>() == turno) {
      
      String backendId = (*it).containsKey("backend_id") ? (*it)["backend_id"].as<String>() : "";
      
      if (isOnline && WiFi.status() == WL_CONNECTED && backendId.length() > 0) {
        HTTPClient http;
  beginHttp(http, backendURL + "/api/asignaciones/" + backendId);
        int httpCode = http.sendRequest("DELETE");
        if (httpCode == 200) addLog("Asignacion borrada en BD remota OK");
        else addLog("Error borrando asignacion remota (Cod: " + String(httpCode) + ")");
        http.end();
      }

      arr.remove(it);
      saveArray("/asignaciones.json", doc);
      server.send(200, "text/plain", "Asignacion eliminada");
      return;
    }
  }
  server.send(404, "text/plain", "Asignacion no encontrada");
}

void handleUltimoRegistro() {
  addLog("[API] GET /ultimo_registro");
  if (!requiereAdmin(server)) return;
  actualizarBloqueoAsistencia(); // No se necesita un bloqueo severo de 120s aquí.
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

void handleGetPersonas() { addLog("[API] GET /api/personas"); if (!requiereAdmin(server)) return; actualizarBloqueoAsistencia(); servirArchivo("/personas.json", "application/json"); }
void handleGetTurnos() { addLog("[API] GET /api/turnos"); if (!requiereAdmin(server)) return; actualizarBloqueoAsistencia(); servirArchivo("/turnos.json", "application/json"); }
void handleGetAsignaciones() { addLog("[API] GET /api/asignaciones"); if (!requiereAdmin(server)) return; actualizarBloqueoAsistencia(); servirArchivo("/asignaciones.json", "application/json"); }
void handleGetAsistencias() { addLog("[API] GET /api/asistencias (public)"); actualizarBloqueoAsistencia(); servirArchivo("/asistencias.json", "application/json"); }

void WiFiEvent(arduino_event_id_t event, arduino_event_info_t info) {
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
      addLog("WiFi: Conectado al AP");
      break;
    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      wifiUptimeStart = millis();
      break;
    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED: {
      wifiDisconnectCount++;
      uint8_t reason = info.wifi_sta_disconnected.reason;
      char buf[64];
      snprintf(buf, sizeof(buf), "WiFi: Desconectado (razon %d, contador %d)", reason, wifiDisconnectCount);
      wifiDisconnectReason = String(buf);
      addLog(wifiDisconnectReason);
      break;
    }
    default: break;
  }
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  pinMode(PIR_PIN, INPUT_PULLDOWN);
  addLog("Calibrando sensor PIR...");
  delay(3000);
  pinMode(13, INPUT_PULLUP);
  pinMode(FLASH_PIN, OUTPUT);
  digitalWrite(FLASH_PIN, LOW);
  ledcAttach(FLASH_PIN, FLASH_PWM_FREQ, FLASH_PWM_RES);
  ledcWrite(FLASH_PIN, 0);
  if (digitalRead(13) == LOW) {
    delay(1000);
    if (digitalRead(13) == LOW) {
      initLittleFS(); saveConfig("", "", backendURL, mqttBroker, ""); Serial.println("RESET DETECTADO");
    }
  }
  
  Serial.begin(115200); delay(1000);

  WiFi.onEvent(WiFiEvent);

  initCamera(); delay(500);

  pinMode(GREEN_LED_PIN, OUTPUT);
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, HIGH); delay(100);
  digitalWrite(GREEN_LED_PIN, LOW);

  initLittleFS(); delay(500); loadWiFiConfig(); tryConnectWiFi();
  
  if (isOnline) {
    sincronizarPendientes();
    sincronizarPersonasDesdeBackend();
    sincronizarTurnosDesdeBackend();
    sincronizarAsignacionesDesdeBackend();
  } else {
      delay(500);
      WiFi.mode(WIFI_AP);
      delay(150);
      WiFi.softAP(apSSID, apPASS, 6, 0, 4);
      delay(150);
      WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));
      addLog("AP iniciado. IP=" + WiFi.softAPIP().toString() + " | PASS=" + String(apPASS));
  }

  // Rutas HTML
  server.on("/", []() { actualizarBloqueoAsistencia(); servirArchivo("/index.html", "text/html"); });
  server.on("/register", []() { actualizarBloqueoAsistencia(60000); servirArchivo("/register.html", "text/html"); });
  server.on("/gestion", []() { actualizarBloqueoAsistencia(); servirArchivo("/gestion.html", "text/html"); });
  server.on("/personas", []() { actualizarBloqueoAsistencia(); servirArchivo("/personas.html", "text/html"); });
  server.on("/asistencias", []() { actualizarBloqueoAsistencia(); servirArchivo("/asistencias.html", "text/html"); });
  server.on("/turnos", []() { actualizarBloqueoAsistencia(); servirArchivo("/turnos.html", "text/html"); });
  server.on("/asignaciones", []() { actualizarBloqueoAsistencia(); servirArchivo("/asignaciones.html", "text/html"); });
  server.on("/wifi-setup", []() { actualizarBloqueoAsistencia(60000); servirArchivo("/wifi-setup.html", "text/html"); });
  server.on("/logs", []() { servirArchivo("/logs.html", "text/html"); });
  
  // Rutas de Acción
  server.on("/wifi-config", handleWiFiConfig);
  server.on("/registrar", handleRegisterUser);
  server.on("/crear_turno", handleCreateTurn);
  server.on("/asignar", handleAssignTurn);
  server.on("/limpiar", handleLimpiarDatos);
  server.on("/sincronizar", handleSincronizar);
  server.on("/fetch-personas", handleFetchPersonas);
  server.on("/set-backend", handleSetBackend);
  server.on("/editar_persona", handleEditarPersona);
  server.on("/actualizar_rostro", handleActualizarRostroPersona);
  server.on("/agregar_fotos", handleAgregarFotosPersona);
  server.on("/borrar_persona", handleBorrarPersona);
  server.on("/borrar_turno", handleBorrarTurno);
  server.on("/borrar_asignacion", handleBorrarAsignacion);
  
  // Rutas API REST
  server.on("/api/personas", handleGetPersonas);
  server.on("/api/turnos", handleGetTurnos);
  server.on("/api/asignaciones", handleGetAsignaciones);
  server.on("/api/asistencias", handleGetAsistencias);
  server.on("/api/logs", []() {
    addLog("[API] GET /api/logs");
    if (!requiereAdmin(server)) return;
    String contenido = logBuffer;
    if (contenido.length() == 0) contenido = "Sin logs disponibles";
    addLog("[API] /api/logs -> 200 (" + String(contenido.length()) + " bytes)");
    server.send(200, "text/html", contenido);
  });
  server.on("/api/logs/clear", []() {
    addLog("[API] GET /api/logs/clear");
    if (!requiereAdmin(server)) return;
    logBuffer = "";
    addLog("[API] /api/logs/clear -> 200");
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
    json += "\"mqtt\":\""    + mqttBroker + "\",";
    json += "\"ssid\":\""    + jsonEscape(savedSSID) + "\",";
    json += "\"enrolado\":"  + String(estaEnrolado ? "true" : "false") + ",";
    json += "\"admin_protegido\":" + String(adminHash.length() > 0 ? "true" : "false") + ",";
    json += "\"mac\":\""     + deviceMAC + "\"";
    json += "}";
    server.send(200, "application/json", json);
  });

  server.on("/wifi-diag", []() {
    String json = "{";
    json += "\"online\":" + String(isOnline ? "true" : "false") + ",";
    json += "\"ssid\":\"" + jsonEscape(savedSSID) + "\",";
    json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
    json += "\"ip\":\"" + (WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : "—") + "\",";
    json += "\"mac\":\"" + deviceMAC + "\",";
    String canal = "N/A";
    if (isOnline) canal = String(WiFi.channel());
    json += "\"canal\":" + canal + ",";
    json += "\"disconnects\":" + String(wifiDisconnectCount) + ",";
    json += "\"last_disconnect_reason\":\"" + jsonEscape(wifiDisconnectReason) + "\",";
    unsigned long uptime = (wifiUptimeStart > 0 && isOnline) ? (millis() - wifiUptimeStart) / 1000 : 0;
    json += "\"wifi_uptime_seg\":" + String(uptime) + ",";
    json += "\"heap_free\":" + String(ESP.getFreeHeap()) + ",";
    json += "\"uptime_total_seg\":" + String(millis() / 1000);
    json += "}";
    server.send(200, "application/json", json);
  });

  server.begin();
  addLog("Sistema web iniciado.");
}

// ============================================================
// LOOP PRINCIPAL
// ============================================================
// ============================================================
// LOOP PRINCIPAL
// ============================================================
// ============================================================
// LOOP PRINCIPAL
// ============================================================
void loop() {
  server.handleClient();
  yield();


  if (savedSSID.length() > 0) verificarConexionWiFi();

  if (isOnline && mqtt_client == NULL) mantenerConexionMQTT();
  unsigned long ahora = millis();
  
  if (estadoActual != ESTADO_IDLE && estadoActual != ESTADO_PROCESANDO_ASISTENCIA && (ahora - tiempoUltimoEstado) > TIMEOUT_REGISTRO) {
    addLog("Timeout de registro. Volviendo a inactivo.");
    ledcWrite(FLASH_PIN, 0);
    estadoActual = ESTADO_IDLE;
  }

  // ==========================================================
  // LÓGICA DE ASISTENCIA HÍBRIDA POR DEMANDA (CONTROLADA POR PIR)
  // ==========================================================
  if (estadoActual == ESTADO_IDLE) {
    String motivoAuto = motivoAsistenciaAutomatica(ahora);
    if (!isOnline && motivoAuto != "habilitada" && (ahora - ultimoLogDiagnosticoOffline) > 15000) {
      ultimoLogDiagnosticoOffline = ahora;
      addLog("[OFFLINE] Auto-asistencia inactiva: " + motivoAuto);
    }

    // 1. EL PIR ES EL PORTERO: Solo si detecta movimiento, activamos un "modo alerta" de 15 segundos
    static unsigned long tiempoUltimoMovimiento = 0;
    static bool hayAlguienFrenteAlSensor = false;

    // 1. EL PIR ES EL PORTERO
    if (digitalRead(PIR_PIN) == HIGH) {
      if (!hayAlguienFrenteAlSensor) {
      addLog("Movimiento detectado. Flash ON por 10 segundos...");
      hayAlguienFrenteAlSensor = true;
      tiempoUltimoMovimiento = ahora;
      ledcWrite(FLASH_PIN, FLASH_DUTY_LOW); // Flash ON al detectar
      delay(800);
      return;
    }
      tiempoUltimoMovimiento = ahora;
    }

    // 2. SOLO SI HAY ALGUIEN, USAMOS LA CÁMARA Y LA HUELLA
    if (hayAlguienFrenteAlSensor) {
      
      // --- NUEVO: TIMEOUT DEL PIR (Anti-Bucle) ---
      // Si el sensor no ha vuelto a detectar movimiento en los últimos 15 segundos,
      // asumimos que fue una falsa alarma o la persona se retiró.
      if (ahora - tiempoUltimoMovimiento > 15000) {
          addLog("Sin movimiento 10s. Flash OFF, sistema a reposo.");
          ledcWrite(FLASH_PIN, 0); // Flash OFF al expirar
          hayAlguienFrenteAlSensor = false;
          return; // Salimos del loop inmediatamente para no sacar fotos en falso
      }
      // -------------------------------------------

      // -- INTENTO FACIAL --
      if (isOnline && (ahora - cooldownAsistencia > COOLDOWN_TIEMPO) && (ahora - lastFaceCheck > FACE_CHECK_INTERVAL)) {
        lastFaceCheck = ahora;
        String personaIdEncontrada = identificarPorRostro(); 
        if (personaIdEncontrada != "" && personaIdEncontrada != "unknown") {
            estadoActual = ESTADO_PROCESANDO_ASISTENCIA;
            String res = procesarAsistencia(personaIdEncontrada, "facial");
            addLog(res);
            if (resultadoAsistenciaExitosa(res)) flashExito(); else flashError();
            cooldownAsistencia = millis();
            ledcWrite(FLASH_PIN, 0);
            hayAlguienFrenteAlSensor = false; 
            
            estadoActual = ESTADO_IDLE; 
        }
      }

      // -- SIN INTENTO HUELLA (solo facial) --
    } // Fin del bloque "if (hayAlguienFrenteAlSensor)"
  }

  // ==========================================================
  // FLUJO DE REGISTRO FACIAL
  // ==========================================================
  if (estadoActual == ESTADO_REGISTRO_FACIAL) {
    static unsigned long ultimoIntentoFoto = 0;
    if (ahora - ultimoIntentoFoto > 4000) { 
      ultimoIntentoFoto = ahora;
      intentosFacial++;
      
      bool excedido = (fotosTomadas >= FOTOS_REQUERIDAS) || (intentosFacial > 15);
      
      if (excedido && fotosTomadas == 0) {
        ledcWrite(FLASH_PIN, 0);
        flashError();
        addLog("No se pudo registrar rostro tras multiples intentos");
        ultimoErrorRegistro = "No se pudo registrar rostro tras multiples intentos";
        estadoActual = ESTADO_IDLE;
        nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = "";
        idParaRostro = "";
        modoEdicionRostro = false;
        personaEditandoId = "";
        fotosTomadas = 0;
      } else if (excedido && fotosTomadas > 0) {
        ledcWrite(FLASH_PIN, 0);
        flashExito();
        addLog("Registro completo: " + String(fotosTomadas) + " foto(s) de referencia guardada(s)");
        rostroRegistroExitoso = true;
        ultimoErrorRegistro = "";
        estadoActual = ESTADO_IDLE;
        nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = "";
        idParaRostro = "";
        modoEdicionRostro = false;
        personaEditandoId = "";
        fotosTomadas = 0;
      } else if (fotosTomadas == 0) {
        addLog("Enviando fotografia #" + String(intentosFacial) + " para registro inicial...");
        if (!registrarRostroEnBackend(idParaRostro)) {
          addLog("No se pudo enviar foto por MQTT. Reintentando...");
          if (mqtt_client == NULL && mqttBroker != "") mantenerConexionMQTT();
        }
      } else {
        addLog("Tomando fotografia adicional #" + String(fotosTomadas + 1) + "/" + String(FOTOS_REQUERIDAS) + "...");
        delay(1500);
        if (agregarFotoEnBackend(idParaRostro)) {
          fotosTomadas++;
          if (fotosTomadas >= FOTOS_REQUERIDAS) {
            ledcWrite(FLASH_PIN, 0);
            flashExito();
            addLog("Registro completo: " + String(fotosTomadas) + " fotos de referencia guardadas");
            rostroRegistroExitoso = true;
            ultimoErrorRegistro = "";
            estadoActual = ESTADO_IDLE;
            nombreRegistrando = ""; rutRegistrando = ""; emailRegistrando = "";
            idParaRostro = "";
            modoEdicionRostro = false;
            personaEditandoId = "";
            fotosTomadas = 0;
          } else {
            addLog("Foto adicional OK. Siguiente en 4 segundos...");
          }
        } else {
          addLog("Error en foto adicional. Reintentando...");
        }
      }
    }
  }

  if (mqttConnected && mqtt_client != NULL && (ahora - lastHeartbeat) > 30000UL) {
    lastHeartbeat = ahora;
    String topic = "esp32/heartbeat/" + deviceMAC;
    String payload = "{\"mac\":\"" + deviceMAC + "\",\"t\":" + String(millis()) + ",\"ip\":\"" + WiFi.localIP().toString() + "\"}";
    esp_mqtt_client_publish(mqtt_client, topic.c_str(), payload.c_str(), 0, 0, 0);
  }

  static unsigned long lastSync = 0;
  if (isOnline && (ahora - lastSync) > 300000UL) {
    lastSync = ahora;
    sincronizarPendientes();
  }

  static unsigned long lastErpSync = 0;
  if (isOnline && (ahora - lastErpSync) > 360000UL) {
    lastErpSync = ahora;
    sincronizarErpConfigDesdeBackend();
  }

  static unsigned long lastPwdCheck = 0;
  if (isOnline && (ahora - lastPwdCheck) > 60000UL) {
    lastPwdCheck = ahora;
    verificarPasswordPendiente();
  }

  delay(20);
}
