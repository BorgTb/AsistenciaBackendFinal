// ============================================================
// TEST: LED verde (GPIO 2) + Sensor PIR (GPIO 12)
// Enciende el LED cuando detecta movimiento
// ============================================================

#define PIR_PIN 12
#define GREEN_LED_PIN 2

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(PIR_PIN, INPUT_PULLDOWN);
  pinMode(GREEN_LED_PIN, OUTPUT);
  digitalWrite(GREEN_LED_PIN, LOW);

  // Blink de arranque para confirmar que el LED funciona
  Serial.println("Test LED verde en GPIO 2 + PIR en GPIO 12");
  Serial.println("Blink de arranque en 3...");
  for (int i = 0; i < 3; i++) {
    digitalWrite(GREEN_LED_PIN, HIGH);
    delay(200);
    digitalWrite(GREEN_LED_PIN, LOW);
    delay(200);
  }
  Serial.println("Listo. Esperando movimiento...");
}

void loop() {
  int pirEstado = digitalRead(PIR_PIN);

  if (pirEstado == HIGH) {
    digitalWrite(GREEN_LED_PIN, HIGH);
    Serial.println("MOVIMIENTO DETECTADO -> LED ON");
  } else {
    digitalWrite(GREEN_LED_PIN, LOW);
  }

  delay(100);
}
