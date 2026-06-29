# Registro de resultados — Capítulo 5

Anota aquí los valores reales a medida que vayas ejecutando las pruebas del [PLAN_PRUEBAS_PENDIENTES.md](PLAN_PRUEBAS_PENDIENTES.md). Las tablas tienen las mismas filas/columnas que `memoria.tex`, así que cuando termines solo me pasas este archivo (o me dices "ya está") y yo reemplazo los `____` directamente en el informe.

Puedes ir llenando de a poco, no es necesario completar todo de una sesión.

---

## 1. Costo total del prototipo

| Componente | Cantidad | Costo (CLP) |
|---|---|---|
| ESP32-CAM (cámara OV2640 + microcontrolador) | 1 | |
| Lector de huellas AS608 | 1 | |
| Sensor PIR HC-SR501 | 1 | |
| Fuente de alimentación 5V / 2A | 1 | |
| Cables y conectores Dupont | 1 kit | |
| Placa de pruebas (protoboard) | 1 | |
| Carcasa / soporte impreso en 3D | 1 | |
| **Total** | | |

Notas (ej. componentes que ya tenías, tipo de cambio usado, etc.):
-

---

## 2. Encuestas SUS

### 2.1 Usuarios no técnicos

Número de personas encuestadas: ____

| N.º | Pregunta | Promedio | Tipo |
|---|---|---|---|
| 1 | Creo que me gustaría usar este sistema con frecuencia. | | Positiva |
| 2 | Encontré el sistema innecesariamente complejo. | | Invertida |
| 3 | Pensé que el sistema era fácil de usar. | | Positiva |
| 4 | Creo que necesitaría apoyo de una persona técnica para poder usar este sistema. | | Invertida |
| 5 | Consideré que las funciones del sistema estaban bien integradas. | | Positiva |
| 6 | Pensé que había demasiada inconsistencia en el sistema. | | Invertida |
| 7 | Imagino que la mayoría de las personas aprenderían a usar este sistema rápidamente. | | Positiva |
| 8 | Encontré el sistema muy engorroso de usar. | | Invertida |
| 9 | Me sentí seguro al usar el sistema. | | Positiva |
| 10 | Necesité aprender muchas cosas antes de poder empezar a usar este sistema. | | Invertida |
| | **Puntuación SUS total** | | |

### 2.2 Usuarios técnicos

Número de personas encuestadas: ____

| N.º | Pregunta | Promedio | Tipo |
|---|---|---|---|
| 1 | Creo que me gustaría usar este sistema con frecuencia. | | Positiva |
| 2 | Encontré el sistema innecesariamente complejo. | | Invertida |
| 3 | Pensé que el sistema era fácil de usar. | | Positiva |
| 4 | Creo que necesitaría apoyo de una persona técnica para poder usar este sistema. | | Invertida |
| 5 | Consideré que las funciones del sistema estaban bien integradas. | | Positiva |
| 6 | Pensé que había demasiada inconsistencia en el sistema. | | Invertida |
| 7 | Imagino que la mayoría de las personas aprenderían a usar este sistema rápidamente. | | Positiva |
| 8 | Encontré el sistema muy engorroso de usar. | | Invertida |
| 9 | Me sentí seguro al usar el sistema. | | Positiva |
| 10 | Necesité aprender muchas cosas antes de poder empezar a usar este sistema. | | Invertida |
| | **Puntuación SUS total** | | |

### 2.3 Notas cualitativas (Anexo A: preguntas complementarias)

Respuestas o impresiones destacables de los grupos (para usar en el análisis comparativo y la discusión):
-
-

---

## 3. Métricas de reconocimiento facial

### 3.1 Tiempo de respuesta (sobre 20 ciclos)

| Métrica | Valor |
|---|---|
| Tiempo promedio de captura + codificación | |
| Tiempo promedio de transmisión HTTP (POST octet-stream) | |
| Tiempo promedio de procesamiento DeepFace (identificación 1:N) | |
| Tiempo total promedio del ciclo | |
| Desviación estándar | |

### 3.2 Precisión del reconocimiento

| Métrica | Valor | (N usado) |
|---|---|---|
| Tasa de reconocimiento exitoso (True Positive Rate) | | |
| Tasa de falsos positivos | | |
| Tasa de falsos negativos | | |
| Efectividad del anti-spoofing (fotos/pantallas rechazadas) | | |
| Precisión con iluminación favorable | | |
| Precisión con iluminación desfavorable | | |

### 3.3 Comparación de detectores faciales (MTCNN vs. RetinaFace)

| Detector | Tiempo promedio de detección | Tasa de acierto |
|---|---|---|
| MTCNN | | |
| RetinaFace | | |

### 3.4 Efecto de la caché de embeddings

| Escenario | Tiempo promedio de identificación |
|---|---|
| Caché vacía (primera consulta) | |
| Caché poblada (consultas posteriores) | |
| Reducción porcentual | |

---

## 4. Pruebas de estrés offline

Duración del escenario 1 (desconexión total): ________
Cantidad de ciclos simulados en escenario 2 (intermitente): ________
Días offline antes de reconectar en escenario 3: ________

| Métrica | Sin conexión | Intermitente | Reconexión |
|---|---|---|---|
| Registros generados offline | | | |
| Registros sincronizados correctamente | | | |
| Porcentaje de sincronización | | | |
| Tiempo de sincronización | | | |
| Reintentos automáticos | N/A | | |

Observaciones (errores encontrados, comportamientos inesperados, etc.):
-

---

## 4.5. (Opcional) Estimación de consumo energético

Consumo según datasheet (mA):

| Componente | Activo | Reposo |
|---|---|---|
| ESP32-CAM | | |
| AS608 | | |

Estimación de uso diario:
- Marcaciones estimadas por día: ____
- Tiempo activo por marcación (s): ____
- % del día en estado activo: ____

| Escenario | Consumo promedio estimado (mAh/día) |
|---|---|
| Sin PIR (siempre en espera activa) | |
| Con PIR (lo implementado) | |
| Reducción estimada | |

---

## 5. Checklist de cumplimiento de objetivos específicos

Marca cuando el dato esté listo y compara contra la meta:

- [ ] Objetivo 1 — Costo total ≤ $45.000 CLP → resultado: ____
- [ ] Objetivo 2 — Tiempo de marcación facial < 5 s → resultado: ____
- [ ] Objetivo 2 — Precisión de identificación > 90% → resultado: ____
- [ ] Objetivo 3 — ≥ 1.000 registros offline sin pérdida → resultado: ____
- [ ] Objetivo 4 — SUS ≥ 68 puntos → resultado: ____
- [ ] Objetivo 5 — 100% de paquetes sincronizados tras reconexión → resultado: ____
- [ ] Objetivo 6 — Disponibilidad ≥ 90% en conectividad intermitente → resultado: ____
