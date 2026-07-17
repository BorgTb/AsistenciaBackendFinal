/*
 * test-wifi.ino - Que ajuste de tryConnectWiFi() rompe la conexion?
 *
 * Mi sketch minimo conecta. El firmware completo no. La diferencia esta en
 * los ajustes que tryConnectWiFi() aplica antes de WiFi.begin(). Este boceto
 * prueba cada ajuste por separado, en la misma placa y la misma red, y dice
 * cual es el culpable.
 *
 * Subir SOLO el sketch (nunca "Upload Filesystem Image").
 * Monitor Serie a 115200. Tarda ~1.5 min en recorrer las 5 pruebas.
 */

#include <WiFi.h>
#include "esp_wifi.h"

const char* SSID_TEST = "iPhoneTintin";
const char* PASS_TEST = "agu12355";

const unsigned long TIMEOUT_POR_PRUEBA = 15000;

volatile uint8_t ultimaRazon = 0;

struct Prueba {
  const char* nombre;
  bool sinPowerSave;   // WiFi.setSleep(false) + esp_wifi_set_ps(WIFI_PS_NONE)
  bool soloBG;         // esp_wifi_set_protocol(11B|11G) -> desactiva 11n
  bool txPowerAlto;    // esp_wifi_set_max_tx_power(78)
  bool dnsFijo;        // WiFi.config(INADDR_NONE, ..., dns)
};

// A es la linea base (equivale a mi sketch que SI funciono).
// E replica exactamente lo que hace tryConnectWiFi() en esp32.ino.
Prueba pruebas[] = {
  { "A: linea base (solo WiFi.begin)", false, false, false, false },
  { "B: + solo 11b/g (sin 11n)",       false, true,  false, false },
  { "C: + sin power save + TX 19.5dBm", true, false, true,  false },
  { "D: + DNS fijo con DHCP",          false, false, false, true  },
  { "E: TODO (replica de esp32.ino)",  true,  true,  true,  true  },
};
const int TOTAL = sizeof(pruebas) / sizeof(pruebas[0]);

bool resultado[TOTAL];
uint8_t razonDe[TOTAL];
unsigned long msDe[TOTAL];

const char* razonTexto(uint8_t r) {
  switch (r) {
    case 2:   return "AUTH_EXPIRE";
    case 4:   return "ASSOC_EXPIRE";
    case 5:   return "ASSOC_TOOMANY";
    case 8:   return "ASSOC_LEAVE";
    case 15:  return "4WAY_HANDSHAKE_TIMEOUT (clave)";
    case 39:  return "TIMEOUT";
    case 201: return "NO_AP_FOUND";
    case 202: return "AUTH_FAIL";
    case 203: return "ASSOC_FAIL";
    case 204: return "HANDSHAKE_TIMEOUT";
    case 0:   return "-";
    default:  return "(otro)";
  }
}

void onWiFiEvent(arduino_event_id_t event, arduino_event_info_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    ultimaRazon = info.wifi_sta_disconnected.reason;
  }
}

// Deja la radio en un estado limpio y con los valores por defecto,
// para que un ajuste de una prueba no contamine la siguiente.
void reiniciarRadio() {
  WiFi.disconnect(true, true);
  delay(300);
  WiFi.mode(WIFI_OFF);
  delay(600);
  WiFi.mode(WIFI_STA);
  delay(300);

  // Restaurar defaults explicitamente
  esp_wifi_set_protocol(WIFI_IF_STA,
                        WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N);
  esp_wifi_set_ps(WIFI_PS_MIN_MODEM);
  WiFi.setSleep(true);
  esp_wifi_set_max_tx_power(60);
  // Devuelve la config de IP a DHCP puro
  WiFi.config(IPAddress(0, 0, 0, 0), IPAddress(0, 0, 0, 0), IPAddress(0, 0, 0, 0));
  delay(200);
}

bool ejecutar(const Prueba& p, int idx) {
  Serial.println("\n---------------------------------------");
  Serial.printf("PRUEBA %s\n", p.nombre);
  Serial.println("---------------------------------------");

  reiniciarRadio();
  ultimaRazon = 0;

  if (p.sinPowerSave) {
    WiFi.setSleep(false);
    esp_wifi_set_ps(WIFI_PS_NONE);
    Serial.println("  aplicado: power save OFF");
  }
  if (p.soloBG) {
    esp_err_t e = esp_wifi_set_protocol(WIFI_IF_STA,
                                        WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G);
    Serial.printf("  aplicado: solo 11b/g, 11n DESACTIVADO (err=%d)\n", e);
  }
  if (p.txPowerAlto) {
    esp_wifi_set_max_tx_power(78);
    Serial.println("  aplicado: TX power 19.5 dBm");
  }
  if (p.dnsFijo) {
    IPAddress dns(8, 8, 8, 8);
    bool ok = WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE, dns);
    Serial.printf("  aplicado: DNS fijo 8.8.8.8 con DHCP (ok=%d)\n", ok);
  }

  unsigned long t0 = millis();
  WiFi.begin(SSID_TEST, PASS_TEST);

  while (millis() - t0 < TIMEOUT_POR_PRUEBA) {
    if (WiFi.status() == WL_CONNECTED) {
      unsigned long ms = millis() - t0;
      Serial.printf("\n  >>> CONECTO en %lu ms. IP=%s  RSSI=%d dBm\n",
                    ms, WiFi.localIP().toString().c_str(), WiFi.RSSI());
      resultado[idx] = true;
      razonDe[idx] = 0;
      msDe[idx] = ms;
      return true;
    }
    delay(100);
    if ((millis() - t0) % 3000 < 100) Serial.print(".");
  }

  Serial.printf("\n  >>> FALLO tras %lu ms. Ultima razon=%d (%s)\n",
                TIMEOUT_POR_PRUEBA, ultimaRazon, razonTexto(ultimaRazon));
  resultado[idx] = false;
  razonDe[idx] = ultimaRazon;
  msDe[idx] = 0;
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println("\n\n=========================================");
  Serial.println("  QUE AJUSTE ROMPE LA CONEXION WIFI?");
  Serial.println("=========================================");
  Serial.printf("  Red   : %s\n", SSID_TEST);
  Serial.printf("  Clave : %d caracteres\n", strlen(PASS_TEST));
  Serial.println("\n  Manten el hotspot ENCENDIDO y la pantalla");
  Serial.println("  'Compartir Internet' ABIERTA durante toda la prueba.");

  WiFi.onEvent(onWiFiEvent);
  WiFi.mode(WIFI_STA);
  delay(500);

  for (int i = 0; i < TOTAL; i++) {
    ejecutar(pruebas[i], i);
    delay(1000);
  }

  // ---- Resumen ----
  Serial.println("\n\n=========================================");
  Serial.println("  RESUMEN");
  Serial.println("=========================================");
  for (int i = 0; i < TOTAL; i++) {
    if (resultado[i]) {
      Serial.printf("  [OK   ] %-34s %lu ms\n", pruebas[i].nombre, msDe[i]);
    } else {
      Serial.printf("  [FALLO] %-34s razon %d (%s)\n",
                    pruebas[i].nombre, razonDe[i], razonTexto(razonDe[i]));
    }
  }

  Serial.println("\n--- Lectura del resultado ---");
  if (resultado[0] && !resultado[4]) {
    Serial.println("  A funciona y E falla: el problema esta en el codigo,");
    Serial.println("  no en la red ni en la clave. El ajuste culpable es");
    Serial.println("  la primera prueba que aparezca como FALLO.");
  } else if (resultado[0] && resultado[4]) {
    Serial.println("  A y E funcionan: los ajustes NO son el problema.");
    Serial.println("  Entonces la clave guardada en wifi.json no coincide");
    Serial.println("  con la real, o el fallo anterior fue el hotspot dormido.");
  } else if (!resultado[0]) {
    Serial.println("  Ni siquiera la linea base conecta: el hotspot esta");
    Serial.println("  dormido o apagado. Reactivalo y repite la prueba.");
  }
}

void loop() {
  delay(1000);
}
