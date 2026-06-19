/*
 * test_ap.ino — Sketch minimo para probar el AP del ESP32-CAM
 * Flashealo, busca "ESP32-TEST" en redes WiFi, conectate con pass "test1234".
 */
#include <WiFi.h>

const char* ssid = "ESP32-TEST";
const char* pass = "test1234";

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\nIniciando AP de prueba...");

  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid, pass, 6, 0, 4);
  WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));

  Serial.print("AP: ");
  Serial.print(ssid);
  Serial.print(" / ");
  Serial.println(pass);
  Serial.print("IP: ");
  Serial.println(WiFi.softAPIP());
  Serial.print("MAC: ");
  Serial.println(WiFi.softAPmacAddress());
}

void loop() {
  delay(10000);
  Serial.print(".");
}
