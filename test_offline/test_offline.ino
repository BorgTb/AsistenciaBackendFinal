#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>
#include <Adafruit_Fingerprint.h>

// Sensor de huellas (RX=GPIO13, TX=GPIO12)
HardwareSerial FingerSerial(2);  
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&FingerSerial);

WebServer server(80);

// ===== AP para configuración =====
const char* apSSID = "ESP32-ASISTENCIA";
const char* apPASS = "12345678";
const char* hostname = "esp32-cam-asistence"; // Custom Name

// ===== Variables WiFi configurables =====
String savedSSID = "";
String savedPASS = "";
bool wifiConfigMode = true;

unsigned long bootEpoch = 0; // se setea cuando hay WiFi con NTP

// ===== Variables para escaneo automático =====
unsigned long lastFingerCheck = 0;
const unsigned long FINGER_CHECK_INTERVAL = 500;
int lastFingerID = -1;
unsigned long lastFingerTime = 0;
const unsigned long FINGER_DEBOUNCE = 3000;


enum EstadoSistema {
  ESTADO_IDLE,
  ESTADO_ESPERANDO_HUELLA_REGISTRO,
  ESTADO_REGISTRO_SEGUNDA_HUELLA,
  ESTADO_MARCANDO
};

EstadoSistema estadoActual = ESTADO_IDLE;
int slotRegistrando = -1;
String nombreRegistrando = "";
String rutRegistrando = "";
String emailRegistrando = "";
unsigned long tiempoUltimoEstado = 0;
const unsigned long TIMEOUT_REGISTRO = 30000;

// ======================= INICIALIZAR SPIFFS ==========================
void initSPIFFS() {
  if (!SPIFFS.begin(true)) {
    addLog("Error montando SPIFFS");
    return;
  }

  const char* files[] = {
    "/personas.json",
    "/turnos.json",
    "/asignaciones.json",
    "/asistencias.json",
    "/wifi.json"
  };

  for (auto f : files) {
    if (!SPIFFS.exists(f)) {
      File file = SPIFFS.open(f, "w");
      if (String(f) == "/wifi.json") {
        file.println("{\"ssid\":\"\",\"pass\":\"\"}");
      } else {
        file.println("[]");
      }
      file.close();
      Serial.printf("Creado %s\n", f);
    }
  }
  
  addLog("SPIFFS inicializado");
}

// ======================= CARGAR/GUARDAR WIFI =========================
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

unsigned long getTimestamp() {
  if (bootEpoch > 0) return bootEpoch + millis() / 1000;
  return millis() / 1000; // fallback offline
}


// Variable global para guardar logs
String logBuffer = "";

void addLog(String msg) {
  Serial.println(msg);  // ← esto, no addLog(msg)
  logBuffer += msg + "<br>";
  if (logBuffer.length() > 3000) {
    logBuffer = logBuffer.substring(logBuffer.length() - 3000);
  }
}


// ======================= FUNCIONES JSON =============================
JsonArray loadArray(const char* path, DynamicJsonDocument &doc) {
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
  if (err || !doc.is<JsonArray>()) {
    doc.set(JsonArray());
  }
  return doc.as<JsonArray>();
}

void saveArray(const char* path, DynamicJsonDocument &doc) {
  File file = SPIFFS.open(path, "w");
  serializeJson(doc, file);
  file.close();
}

// ======================= BUSCAR SLOT LIBRE DE HUELLA =================
int encontrarSlotLibre() {
  for (int id = 1; id < 127; id++) {
    if (finger.loadModel(id) != FINGERPRINT_OK)
      return id;
  }
  return -1;
}

// ======================= ENROLL HUELLA ===============================
bool registrarHuella(int slot) {
  Serial.printf("Iniciando enrolamiento en slot %d...\n", slot);

  int p = -1;
  int intentos = 0;

  addLog("Coloque el dedo...");
  while (p != FINGERPRINT_OK && intentos < 50) {
    p = finger.getImage();
    delay(100);
    intentos++;
  }
  
  if (p != FINGERPRINT_OK) {
    addLog("Timeout esperando dedo");
    return false;
  }

  p = finger.image2Tz(1);
  if (p != FINGERPRINT_OK) {
    addLog("Error procesando imagen 1");
    return false;
  }

  addLog("Retire el dedo");
  delay(2000);

  p = -1;
  intentos = 0;
  addLog("Coloque nuevamente el mismo dedo...");
  while (p != FINGERPRINT_OK && intentos < 50) {
    p = finger.getImage();
    delay(100);
    intentos++;
  }
  
  if (p != FINGERPRINT_OK) {
    addLog("Timeout en segunda captura");
    return false;
  }

  p = finger.image2Tz(2);
  if (p != FINGERPRINT_OK) {
    addLog("Error procesando imagen 2");
    return false;
  }

  p = finger.createModel();
  if (p != FINGERPRINT_OK) {
    addLog("Error creando modelo");
    return false;
  }

  p = finger.storeModel(slot);
  if (p == FINGERPRINT_OK) {
    addLog("Huella guardada correctamente");
    return true;
  }

  addLog("Error guardando huella");
  return false;
}

// ======================= CONFIGURAR WIFI =============================
void handleWiFiConfig() {
  if (server.hasArg("ssid") && server.hasArg("pass")) {
    String ssid = server.arg("ssid");
    String pass = server.arg("pass");
    
    saveWiFiConfig(ssid, pass);
    server.send(200, "text/plain", "Configuracion guardada. Reiniciando...");
    delay(1000);
    ESP.restart();
  } else {
    server.send(400, "text/plain", "Faltan parametros");
  }
}

// ======================= REGISTRAR PERSONA ===========================
void handleRegisterUser() {
  if (!server.hasArg("name") || !server.hasArg("rut") || !server.hasArg("email")) {
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

  // Guardar datos temporalmente y cambiar estado
  slotRegistrando = slot;
  nombreRegistrando = server.arg("name");
  rutRegistrando = rut;
  emailRegistrando = server.arg("email");
  estadoActual = ESTADO_ESPERANDO_HUELLA_REGISTRO;
  tiempoUltimoEstado = millis();

  // Retorna inmediatamente — el loop maneja el resto
  server.send(200, "text/plain", "Coloque el dedo en el sensor...");
}

// ======================= CREAR TURNO ===============================
void handleCreateTurn() {
  if (!server.hasArg("nombre") ||
      !server.hasArg("inicio") ||
      !server.hasArg("fin") ||
      !server.hasArg("dias")) {
    server.send(400, "text/plain", "Datos incompletos");
    return;
  }

  DynamicJsonDocument doc(1024); 
  JsonArray turnos = loadArray("/turnos.json", doc);

  JsonObject t = turnos.createNestedObject();
  t["id"] = String(turnos.size() + 1);
  t["nombre"] = server.arg("nombre");
  t["inicio"] = server.arg("inicio");
  t["fin"] = server.arg("fin");
  t["dias"] = server.arg("dias");

  saveArray("/turnos.json", doc);
  server.send(200, "text/plain", "Turno creado");
}

// ======================= ASIGNAR TURNO =============================
void handleAssignTurn() {
  if (!server.hasArg("persona") || !server.hasArg("turno")) {
    server.send(400, "text/plain", "Falta persona o turno");
    return;
  }

  DynamicJsonDocument doc(1024);
  JsonArray asignaciones = loadArray("/asignaciones.json", doc);

  String personaId = server.arg("persona");
  String turnoId = server.arg("turno");
  
  for (JsonObject a : asignaciones) {
    if (a["persona_id"] == personaId) {
      server.send(400, "text/plain", "Persona ya tiene turno asignado");
      return;
    }
  }

  JsonObject a = asignaciones.createNestedObject();
  a["persona_id"] = personaId;
  a["turno_id"] = turnoId;
  a["fecha_asignacion"] = millis() / 1000;

  saveArray("/asignaciones.json", doc);
  server.send(200, "text/plain", "Turno asignado");
}

// ======================= VERIFICAR TURNO ACTIVO =====================
bool turnoActivo(const String& personaId) {
  DynamicJsonDocument doc(2048);  // la mitad de RAM
  JsonArray asign = loadArray("/asignaciones.json", doc);
  for (JsonObject a : asign) {
    if (a["persona_id"] == personaId) return true;
  }
  return false;
}
// ======================= REGISTRAR ASISTENCIA =======================
String registrarAsistenciaAutomatica(int huellaID) {
  DynamicJsonDocument docP(2048);
  JsonArray personas = loadArray("/personas.json", docP);

  String personaId = "";
  String nombre = "";

  for (JsonObject p : personas) {
    if (p["huella_id"] == huellaID) {
      personaId = p["id"].as<String>();
      nombre = p["nombre"].as<String>();
      break;
    }
  }

  if (personaId == "") {
    return "Huella no asociada a usuario";
  }

  if (!turnoActivo(personaId)) {
    return "Usuario sin turno asignado: " + nombre;
  }

  DynamicJsonDocument docA(2048);
  JsonArray asist = loadArray("/asistencias.json", docA);

  String tipo = "entrada";
  for (int i = asist.size() - 1; i >= 0; i--) {
    JsonObject a = asist[i];
    if (a["persona_id"] == personaId) {
      tipo = (a["tipo"] == "entrada") ? "salida" : "entrada";
      break;
    }
  }

  JsonObject a = asist.createNestedObject();
  a["persona_id"] = personaId;
  a["nombre"] = nombre;
  a["tipo"] = tipo;
  a["timestamp"] = millis() / 1000;
  a["sincronizado"] = false;  // ← AGREGAR ESTA LÍNEA

  saveArray("/asistencias.json", docA);

  String tipoMayus = tipo;
  tipoMayus.toUpperCase();
  return tipoMayus + " registrada\nUsuario: " + nombre;
}

void handleMarcarAsistencia() {
  addLog("Esperando huella...");

  int p = finger.getImage();
  if (p != FINGERPRINT_OK) {
    server.send(500, "text/plain", "No se detecta huella");
    return;
  }

  // ✅ REEMPLAZAR POR
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

  int huellaID = finger.fingerID;
  Serial.printf("Huella reconocida: ID %d\n", huellaID);

  String resultado = registrarAsistenciaAutomatica(huellaID);
  server.send(200, "text/plain", resultado);
}

// ======================= APIs REST ===============================
void handleGetPersonas() {
  File file = SPIFFS.open("/personas.json", "r");
  String content = file.readString();
  file.close();
  server.send(200, "application/json", content);
}

void handleGetTurnos() {
  File file = SPIFFS.open("/turnos.json", "r");
  String content = file.readString();
  file.close();
  server.send(200, "application/json", content);
}

void handleGetAsignaciones() {
  File file = SPIFFS.open("/asignaciones.json", "r");
  String content = file.readString();
  file.close();
  server.send(200, "application/json", content);
}

void handleGetAsistencias() {
  File file = SPIFFS.open("/asistencias.json", "r");
  String content = file.readString();
  file.close();
  server.send(200, "application/json", content);
}

// ======================= LIMPIAR DATOS ===============================
void handleLimpiarDatos() {
  if (!server.hasArg("codigo")) {
    server.send(400, "text/plain", "Falta codigo de seguridad");
    return;
  }

  String codigo = server.arg("codigo");
  
  if (codigo != "1234") {
    server.send(403, "text/plain", "Codigo incorrecto");
    return;
  }

  addLog("\nLIMPIANDO TODOS LOS DATOS...");

  const char* files[] = {
    "/personas.json",
    "/turnos.json",
    "/asignaciones.json",
    "/asistencias.json"
  };

  for (auto f : files) {
    File file = SPIFFS.open(f, "w");
    file.println("[]");
    file.close();
    Serial.printf("Limpiado %s\n", f);
  }

  addLog("Limpiando huellas del sensor...");
  for (int id = 1; id < 127; id++) {
    finger.deleteModel(id);
  }

  addLog("Todos los datos han sido eliminados\n");
  server.send(200, "text/plain", "Sistema limpiado correctamente\n\nSe eliminaron:\n- Todas las personas\n- Todos los turnos\n- Todas las asignaciones\n- Todas las asistencias\n- Todas las huellas del sensor");
}

// ======================= PAGINA DE CONFIGURACION WIFI ================
const char* wifiConfigPage = R"rawliteral(

)rawliteral";

// ======================= HTML PRINCIPAL ===============================


void servirArchivo(const char* path, const char* tipo) {
  if (!SPIFFS.exists(path)) {
    server.send(404, "text/plain", "Archivo no encontrado");
    return;
  }
  File f = SPIFFS.open(path, "r");
  server.streamFile(f, tipo);
  f.close();
}

// ======================= SETUP ===========================
void setup() {
  Serial.begin(115200);
  delay(1000);
  addLog("\n\nESP32 Sistema de Asistencia Offline");
  addLog("========================================");
  
  FingerSerial.begin(57600, SERIAL_8N1, 14, 15);
  finger.begin(57600);
  
  if (finger.verifyPassword()) {
    addLog("Sensor de huellas conectado");
  } else {
    addLog("Sensor de huellas NO detectado");
    addLog("Verifique las conexiones:");
    addLog("   RX (amarillo) -> GPIO 13");
    addLog("   TX (blanco)   -> GPIO 12");
    addLog("   VCC (rojo)    -> 5V");
    addLog("   GND (negro)   -> GND");
  }
  
  initSPIFFS();
  loadWiFiConfig();
  
  WiFi.mode(WIFI_AP);
  WiFi.setTxPower(WIFI_POWER_11dBm);
  WiFi.softAP(apSSID, apPASS, 1, 0, 4);
  
  IPAddress local_IP(192,168,4,1);
  IPAddress gateway(192,168,4,1);
  IPAddress subnet(255,255,255,0);
  WiFi.softAPConfig(local_IP, gateway, subnet);
  
  addLog("\nPunto de Acceso WiFi:");
  Serial.printf("   SSID: %s\n", apSSID);
  Serial.printf("   Pass: %s\n", apPASS);
  Serial.printf("   IP:   %s\n", WiFi.softAPIP().toString().c_str());
  Serial.printf("   Canal: 1\n");
  Serial.printf("   Potencia: MAXIMA (19.5dBm)\n\n");

server.on("/", []() { 
  servirArchivo("/index.html", "text/html"); 
});
server.on("/register", []() { 
  servirArchivo("/register.html", "text/html"); 
});
server.on("/gestion", []() { 
  servirArchivo("/gestion.html", "text/html"); 
});
server.on("/personas", []() { 
  servirArchivo("/personas.html", "text/html"); 
});
server.on("/asistencias", []() { 
  servirArchivo("/asistencias.html", "text/html"); 
});
server.on("/turnos", []() { 
  servirArchivo("/turnos.html", "text/html"); 
});
server.on("/asignaciones", []() { 
  servirArchivo("/asignaciones.html", "text/html"); 
});
server.on("/wifi-setup", []() { 
  servirArchivo("/wifi-setup.html", "text/html"); 
});


  
  server.on("/wifi-config", handleWiFiConfig);
  server.on("/registrar", handleRegisterUser);
  server.on("/crear_turno", handleCreateTurn);
  server.on("/asignar", handleAssignTurn);
  server.on("/marcar", handleMarcarAsistencia);
  server.on("/api/personas", handleGetPersonas);
  server.on("/api/turnos", handleGetTurnos);
  server.on("/api/asignaciones", handleGetAsignaciones);
  server.on("/api/asistencias", handleGetAsistencias);
  server.on("/limpiar", handleLimpiarDatos);
  // Agregar en setup() dentro de las rutas:
  server.on("/estado", []() {
    String estado = (estadoActual == ESTADO_IDLE) ? "listo" : "ocupado";
    server.send(200, "text/plain", estado);
  });
  // Ruta para ver logs desde el navegador
server.on("/logs", []() {
  String html = "<!DOCTYPE html><html><head>";
  html += "<meta charset='utf-8'>";
  html += "<meta http-equiv='refresh' content='2'>"; // refresca sola
  html += "<title>Logs</title></head><body>";
  html += "<h3>Log del sistema</h3>";
  html += "<div style='font-family:monospace;font-size:12px'>";
  html += logBuffer;
  html += "</div></body></html>";
  server.send(200, "text/html", html);
});

  server.begin();
  addLog("Servidor web iniciado");
  addLog("Acceda desde: http://" + WiFi.softAPIP().toString());
  addLog("\n========================================");
  addLog("Sistema listo para usar");
}

void completarRegistroPersona() {
  DynamicJsonDocument doc(2048);
  JsonArray personas = loadArray("/personas.json", doc);

  JsonObject p = personas.createNestedObject();
  p["id"] = String(personas.size());
  p["nombre"] = nombreRegistrando;
  p["rut"] = rutRegistrando;
  p["email"] = emailRegistrando;
  p["huella_id"] = slotRegistrando;
  p["fecha_registro"] = getTimestamp();
  p["sincronizado"] = false;

  saveArray("/personas.json", doc);
  addLog("Persona guardada: " + nombreRegistrando);

  slotRegistrando = -1;
  nombreRegistrando = "";
  rutRegistrando = "";
  emailRegistrando = "";
}

// ======================= LOOP ============================
void loop() {
  server.handleClient();
  
  unsigned long ahora = millis();
  
  // Timeout de seguridad para estados bloqueados
  if (estadoActual != ESTADO_IDLE && 
      (ahora - tiempoUltimoEstado) > TIMEOUT_REGISTRO) {
    addLog("Timeout: volviendo a IDLE");
    estadoActual = ESTADO_IDLE;
  }

  // Solo escanear huella cada 500ms y solo en IDLE
  // Manejar registro de primera huella
  if (estadoActual == ESTADO_ESPERANDO_HUELLA_REGISTRO) {
    int p = finger.getImage();
    if (p == FINGERPRINT_OK) {
      p = finger.image2Tz(1);
      if (p == FINGERPRINT_OK) {
        addLog("Primera huella OK, retire el dedo...");
        estadoActual = ESTADO_REGISTRO_SEGUNDA_HUELLA;
        tiempoUltimoEstado = millis();
      }
    }
    return;
  }

  // Manejar registro de segunda huella
  if (estadoActual == ESTADO_REGISTRO_SEGUNDA_HUELLA) {
    int p = finger.getImage();
    if (p == FINGERPRINT_NOFINGER) return; // esperar que retire dedo
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
          addLog("Huellas no coinciden, intente nuevamente");
          estadoActual = ESTADO_ESPERANDO_HUELLA_REGISTRO;
          tiempoUltimoEstado = millis();
          return;
        }
      }
      estadoActual = ESTADO_IDLE;
    }
    return;
  }
}
