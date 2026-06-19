/*
 * factory_reset.ino — Limpia LittleFS, borra configuracion,
 *                     y reinicia el ESP32-CAM en modo AP limpio.
 *
 * 1. Flasheá este sketch.
 * 2. Esperá a que el LED verde parpadee (borrado completo).
 * 3. Flasheá el firmware real de vuelta.
 */

#include <LittleFS.h>
#include <WiFi.h>

#define LED_VERDE 2
#define FLASH_PIN 4

const char* apSSID = "ESP32-ASISTENCIA";
const char* apPASS = "Asistencia2026";

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n========== FACTORY RESET ==========");

  pinMode(LED_VERDE, OUTPUT);
  pinMode(FLASH_PIN, OUTPUT);
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(FLASH_PIN, LOW);

  // 1. Formatear LittleFS (borra TODO: wifi.json, admin.json, personas, asistencias...)
  Serial.print("Formateando LittleFS... ");
  LittleFS.format();
  Serial.println("LISTO");

  // 2. Montar y crear archivos por defecto
  Serial.print("Montando LittleFS... ");
  if (!LittleFS.begin(true)) {
    Serial.println("ERROR");
    return;
  }
  Serial.println("LISTO");

  // 3. Crear archivos vacios
  const char* files[] = {"/personas.json", "/turnos.json", "/asignaciones.json", "/asistencias.json", "/wifi.json", "/admin.json"};
  for (auto f : files) {
    digitalWrite(LED_VERDE, !digitalRead(LED_VERDE));
    delay(100);
    digitalWrite(FLASH_PIN, !digitalRead(FLASH_PIN));
    delay(100);
    digitalWrite(FLASH_PIN, LOW);

    Serial.print("Creando "); Serial.print(f); Serial.print("... ");
    auto file = LittleFS.open(f, "w");
    if (String(f) == "/wifi.json") {
      file.println("{\"ssid\":\"\",\"pass\":\"\",\"backend\":\"http://172.20.10.3:5000\",\"mqtt\":\"\",\"pin\":\"\"}");
    } else if (String(f) == "/admin.json") {
      file.println("{}");
    } else {
      file.println("[]");
    }
    file.close();
    Serial.println("LISTO");
  }

  // 4. Iniciar AP limpio
  Serial.println("\nIniciando AP...");
  WiFi.mode(WIFI_AP);
  WiFi.softAP(apSSID, apPASS, 6, 0, 4);
  WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));
  Serial.print("AP iniciado: ");
  Serial.print(apSSID);
  Serial.print(" / ");
  Serial.println(apPASS);
  Serial.print("IP: ");
  Serial.println(WiFi.softAPIP());

  // 5. Indicar fin con 5 parpadeos rapidos
  for (int i = 0; i < 5; i++) {
    digitalWrite(LED_VERDE, HIGH);
    delay(150);
    digitalWrite(LED_VERDE, LOW);
    delay(150);
  }

  Serial.println("========== FIN DEL RESET ==========");
  Serial.println("Ya podes flashear el firmware principal.");
}

void loop() {
  delay(10000);
  digitalWrite(LED_VERDE, !digitalRead(LED_VERDE));
}
