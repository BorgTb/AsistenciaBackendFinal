// Pines de tu proyecto
#define PIR_PIN 12
#define FLASH_PIN 4

void setup() {
  // Iniciamos el monitor serie para ver los mensajes en la PC
  Serial.begin(115200);
  delay(1000); // Esperamos a que el monitor serie abra
  
  Serial.println("\n--- INICIANDO TEST DE SENSOR PIR ---");
  
  // Configuramos el PIR con PULLDOWN para evitar el efecto antena (falsos positivos)
  pinMode(PIR_PIN, INPUT_PULLDOWN); 
  
  // Configuramos el LED Flash y lo apagamos por defecto
  pinMode(FLASH_PIN, OUTPUT);
  digitalWrite(FLASH_PIN, LOW);
  
  Serial.println("Esperando 10 segundos para que el sensor PIR se estabilice...");
  delay(10000); // Los PIR necesitan unos segundos al arrancar para "leer" la temperatura del cuarto
  Serial.println("¡Test Listo! Pasa tu mano frente al sensor.");
}

void loop() {
  // Leemos el voltaje del pin 12
  int estadoPIR = digitalRead(PIR_PIN);

  if (estadoPIR == HIGH) {
    // Si hay movimiento: Prendemos la luz y avisamos por consola
    digitalWrite(FLASH_PIN, HIGH);
    Serial.println("✋ ¡Movimiento detectado! (HIGH)");
    
  } else {
    // Si no hay movimiento: Apagamos la luz
    digitalWrite(FLASH_PIN, LOW);
  }

  // Una pequeña pausa para no saturar el procesador
  delay(100); 
}
