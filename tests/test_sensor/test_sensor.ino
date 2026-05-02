#include <WiFi.h>
#include <WebServer.h>

// Mismos ajustes de tu código principal
const char* ssid = "ESP32-ASISTENCIA";
const char* password = "12345678";

#define PIR_PIN 12
#define FLASH_PIN 4

WebServer server(80);
String webLogs = ""; // Aquí guardaremos lo que pase

void addLog(String msg) {
  String timestamp = String(millis() / 1000);
  String nuevaLinea = "[" + timestamp + "s] " + msg;
  Serial.println(nuevaLinea); // Por si acaso
  webLogs = nuevaLinea + "<br>" + webLogs; // El log más nuevo arriba
  
  // Limitar tamaño para no agotar la RAM
  if (webLogs.length() > 2000) webLogs = webLogs.substring(0, 2000);
}

// Página Web Simple
void handleRoot() {
  String html = "<html><head><meta charset='UTF-8'><meta http-equiv='refresh' content='2'>";
  html += "<title>Monitor de Logs WiFi</title>";
  html += "<style>body{background:#111;color:#0f0;font-family:monospace;padding:20px;} h2{color:#fff;}</style></head><body>";
  html += "<h2>Monitor de Sensor AM312</h2>";
  html += "<p>Estado actual: <b>" + String(digitalRead(PIR_PIN) == HIGH ? "MOVIMIENTO" : "CALMA") + "</b></p>";
  html += "<hr><div id='logs'>" + webLogs + "</div>";
  html += "</body></html>";
  server.send(200, "text/html", html);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  pinMode(FLASH_PIN, OUTPUT);

  // Configurar como Access Point
  WiFi.softAP(ssid, password);
  IPAddress IP = WiFi.softAPIP();
  
  server.on("/", handleRoot);
  server.begin();

  addLog("Servidor de logs iniciado");
  addLog("Conéctate a WiFi: " + String(ssid));
  addLog("Abre en tu móvil: http://" + IP.toString());
}

void loop() {
  server.handleClient();

  static int ultimoEstado = LOW;
  int estadoActual = digitalRead(PIR_PIN);

  // Detectar cambios en el sensor
  if (estadoActual != ultimoEstado) {
    if (estadoActual == HIGH) {
      addLog("!!! MOVIMIENTO DETECTADO !!!");
      digitalWrite(FLASH_PIN, HIGH);
      delay(200); // Destello rápido
      digitalWrite(FLASH_PIN, LOW);
    } else {
      addLog("... El sensor volvió a calma");
    }
    ultimoEstado = estadoActual;
  }
  
  delay(50); 
}
