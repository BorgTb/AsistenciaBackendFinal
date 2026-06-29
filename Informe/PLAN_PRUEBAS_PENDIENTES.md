# Plan de pruebas para completar el Capítulo 5

Este documento lista, en orden recomendado de ejecución, todas las mediciones y pruebas que faltan para reemplazar los placeholders `____` del informe (`memoria.tex`, Capítulo 5: Análisis de resultados). Para cada bloque se indica: qué medir, cómo medirlo, y en qué tabla/sección del informe va el resultado.

---

## 0. Antes de empezar

- [ ] Tener el prototipo ESP32-CAM armado y enrolado contra el backend (con al menos 1 empresa de prueba creada).
- [ ] Tener PostgreSQL y el broker Mosquitto corriendo (vía `docker-compose up`).
- [ ] Tener un grupo de **al menos 5-8 personas no técnicas** (trabajadores/empleadores) y **3-5 personas técnicas** (devs/integradores) disponibles para las encuestas SUS. Cuantas más personas, más confiable el promedio.
- [ ] Tener registradas en el sistema al menos 5-10 personas con rostro de referencia, para las pruebas de reconocimiento facial.

---

## 1. Costo total del prototipo
**Tabla destino:** `tab:costos` (Sección 5.1)

Junta las boletas/cotizaciones reales de cada componente que compraste. Si algún componente lo conseguiste gratis o ya lo tenías, indícalo como tal en vez de inventar un precio (o pon el precio de mercado actual si quieres mantener el análisis de viabilidad económica honesto).

| Componente | Qué anotar |
|---|---|
| ESP32-CAM | Precio pagado o de mercado (CLP) |
| Lector de huellas AS608 | Precio pagado o de mercado |
| Sensor PIR HC-SR501 | Precio pagado o de mercado |
| Fuente de alimentación 5V/2A | Precio pagado o de mercado |
| Cables y conectores Dupont (1 kit) | Precio pagado o de mercado |
| Protoboard | Precio pagado o de mercado |
| Carcasa/soporte 3D | Costo de impresión (filamento + tiempo) o de mercado si la mandaste a hacer |
| **Total** | Suma de todo lo anterior |

> Recuerda: el Objetivo Específico 1 exige que el total **no supere los \$45.000 CLP**. Si te pasas, documenta por qué (ej. importación, alza de precios) en el análisis de resultados.

---

## 2. Encuestas SUS (System Usability Scale)
**Tablas destino:** `tab:sus_notecnicos`, `tab:sus_tecnicos` (Sección 5.2)

### 2.1 Cómo aplicar la encuesta
1. Usa el cuestionario estándar de 10 preguntas ya documentado en la Sección 3.3.2 / Tabla `tab:sus_cuestionario` del informe (estas preguntas **no las cambies**, son el instrumento validado de Brooke 1996).
2. Aplica la encuesta a cada persona **después** de que haya usado el sistema (haga una marcación, o configure el dispositivo, según el grupo):
   - **No técnicos** (trabajadores/empleadores): que prueben marcar asistencia por huella y por rostro, y que un empleador pruebe configurar Wi-Fi y ver el panel.
   - **Técnicos** (devs/integradores): que prueben consumir la API (Postman/cURL) y revisar la documentación.
3. Anexo A del informe ya tiene preguntas complementarias específicas para cada grupo — apícalas también, son útiles para el análisis cualitativo aunque no entren en el puntaje SUS numérico.
4. Escala de respuesta: 1 = "Totalmente en desacuerdo" → 5 = "Totalmente de acuerdo".

### 2.2 Cómo calcular el puntaje (ya documentado en el informe, créditos a Brooke 1996)
Por cada persona:
- Preguntas impares (1,3,5,7,9): puntaje = respuesta − 1
- Preguntas pares (2,4,6,8,10): puntaje = 5 − respuesta
- Suma los 10 valores resultantes y multiplica por 2.5 → puntaje SUS entre 0 y 100.

Promedia los puntajes individuales del grupo para obtener el promedio por pregunta (columna "Promedio" de la tabla) y el puntaje SUS total del grupo.

### 2.3 Qué llenar
- Promedio de cada una de las 10 preguntas (por grupo) → filas de ambas tablas.
- Puntaje SUS total de cada grupo → fila "Puntuación SUS total".
- Comparación entre ambos grupos e interpretación según Bangor et al. (≥70 aceptable, 50-70 marginal, <50 no aceptable) → Sección 5.2.3 "Análisis comparativo" (actualmente solo tiene el texto introductorio, falta el análisis con los números reales).

> Objetivo específico 4 exige SUS ≥ 68 para que se considere cumplido.

---

## 3. Métricas de reconocimiento facial
**Tablas destino:** `tab:tiempos_facial`, `tab:precision_facial` (Sección 5.3)

### 3.1 Tiempos de respuesta (20 ciclos mínimo, ya definido en el informe)
Con el dispositivo y backend corriendo, marca 20 veces por rostro y mide (puedes instrumentar con `time.time()` en el backend antes/después de cada etapa, o usar timestamps en los logs):

| Métrica | Cómo medirla |
|---|---|
| Tiempo de captura + codificación JPEG | Timestamp en el firmware: desde `esp_camera_fb_get()` hasta tener el buffer listo para enviar |
| Tiempo de transmisión HTTP (POST octet-stream) | Timestamp desde que el ESP32 hace el POST hasta que recibe respuesta (puedes medirlo con `millis()` en el firmware) |
| Tiempo de procesamiento DeepFace (1:N) | Timestamp en el backend, justo antes y después de llamar `DeepFace.represent()` / comparación contra embeddings |
| Tiempo total del ciclo | Suma de los anteriores, o medido end-to-end desde el firmware |
| Desviación estándar | Calculada sobre los 20 tiempos totales (Excel, Python `statistics.stdev()`, o similar) |

> Tip: si no quieres instrumentar el firmware, puedes loguear timestamps solo en el backend (recepción, antes/después de DeepFace, respuesta) y aproximar el tiempo de captura+transmisión como "tiempo total − tiempo de procesamiento backend".

> Objetivo específico 2 exige tiempo total **< 5 segundos**.

### 3.2 Precisión del reconocimiento
Diseña un set de pruebas con las personas ya registradas:

| Métrica | Cómo medirla |
|---|---|
| Tasa de reconocimiento exitoso (TPR) | De N intentos de identificación de personas SÍ registradas, cuántos identifican correctamente / N |
| Tasa de falsos positivos | De M intentos con un rostro NO registrado, cuántas veces el sistema identifica erróneamente a alguien / M |
| Tasa de falsos negativos | De N intentos de personas SÍ registradas, cuántas veces el sistema no las reconoce (HTTP 404) / N |
| Efectividad del anti-spoofing | De P intentos con fotos impresas o mostradas en pantalla de un rostro registrado, cuántas son rechazadas por DeepFace / P |
| Precisión con iluminación favorable | Repetir identificación de las mismas personas con buena luz natural/artificial, % de aciertos |
| Precisión con iluminación desfavorable | Repetir con contraluz o luz tenue, % de aciertos |

> Sugerencia de tamaño de muestra mínimo: al menos 20 intentos por fila para que el porcentaje tenga algo de validez estadística (no es obligatorio pero se ve mejor que "3 de 3").

> Objetivo específico 2 exige precisión **> 90%**.

### 3.3 Comparación de detectores faciales (MTCNN vs. RetinaFace)
**Tabla destino:** `tab:comparacion_detectores` (Sección 5.3.3)

Esto respalda con datos propios la afirmación de que MTCNN es más rápido que RetinaFace (hoy solo citada de la literatura).

1. Define un set fijo de imágenes de prueba (ideal: las mismas 20 capturas usadas en 3.1/3.2, para que la comparación sea justa).
2. Configura la variable de entorno `FACIAL_DETECTOR=mtcnn`, reinicia el backend, y corre la identificación sobre todo el set. Anota el tiempo promedio de detección (puedes aislar solo la etapa de detección/extracción de embedding, sin contar transmisión HTTP) y cuántas identificaciones fueron correctas.
3. Repite el mismo set con `FACIAL_DETECTOR=retinaface`.
4. Compara ambos resultados en la tabla.

> No necesitas hardware adicional, es correr la misma prueba dos veces cambiando una variable de entorno.

### 3.4 Efecto de la caché de embeddings
**Tabla destino:** `tab:cache_embeddings` (Sección 5.3.4)

1. Reinicia el backend (esto vacía la caché en memoria) o espera a que expire el TTL configurado en `FACIAL_CACHE_TTL`.
2. Haz una identificación y mide su tiempo total (esta es la consulta con "caché vacía", porque tuvo que ir a la base de datos a buscar y descifrar los embeddings).
3. Inmediatamente después, sin reiniciar nada, haz una segunda identificación y mide su tiempo (esta usa la caché ya poblada).
4. Repite el ciclo (reiniciar → medir frío → medir caliente) varias veces para promediar, y calcula la reducción porcentual: `(tiempo_frío - tiempo_caliente) / tiempo_frío * 100`.

---

## 4. Pruebas de estrés offline
**Tablas destino:** `tab:estres_offline` y `tab:estres_offline_fallas` (Sección 5.4)

Cinco escenarios en total, ya descritos en el informe (Secciones 5.4.1 a 5.4.5): los primeros tres varían la conectividad Wi-Fi, los dos últimos prueban fallas distintas (corte de energía a mitad de sincronización, y backend caído con la red intacta) que no se cubren variando solo la conexión.

### 4.1 Escenario 1: Desconexión total
1. Desconecta el ESP32-CAM de la red Wi-Fi (o apaga el router/AP).
2. Define un período de prueba (sugerido: mínimo 2-4 horas, idealmente 24h si tienes tiempo, para que el resultado sea creíble).
3. Durante ese período, realiza marcaciones periódicas (ej. cada 15-30 min) por huella o rostro.
4. Anota cuántas marcaciones se generaron en total (quedan en LittleFS).
5. Reconecta el Wi-Fi y verifica que el 100% de los registros generados se sincronicen con el backend (compara el conteo en LittleFS antes de sincronizar vs. los registros nuevos en la tabla `asistencias`).

**Llenar:** "Registros generados offline", "Registros sincronizados correctamente", "Porcentaje de sincronización" (columna "Sin conexión").

### 4.2 Escenario 2: Conectividad intermitente
1. Simula cortes de red repetidos (puedes apagar/encender el Wi-Fi del router, o usar el botón de reset del AP, en intervalos aleatorios, ej. cada 2-10 minutos durante 1 hora).
2. Define cuántos ciclos de conexión/desconexión simulaste (anótalo, reemplaza el "____ ciclos").
3. Cuenta cuántos reintentos automáticos hizo el dispositivo (revisa logs del firmware o `addLog()` en el ESP32).
4. Verifica la consistencia del log de eventos (¿hay duplicados o huecos?).

**Llenar:** columna "Intermitente" de la tabla + el número de ciclos simulados en el texto.

### 4.3 Escenario 3: Reconexión prolongada
1. Deja el dispositivo offline por varios días (sugerido: 2-3 días mínimo, ajusta según el tiempo que tengas antes de la entrega).
2. Anota cuántos días estuvo offline (reemplaza "____ días").
3. Reconecta y mide el tiempo que toma sincronizar todas las marcaciones acumuladas (puedes medirlo con un cronómetro desde que detecta conexión hasta que el log indica sincronización completa).
4. Verifica que ningún registro se haya perdido o corrompido.

**Llenar:** columna "Reconexión" de la tabla `tab:estres_offline`.

### 4.4 Escenario 4: Corte de energía durante la sincronización
1. Genera un lote de al menos 10 marcaciones offline (repite los pasos del Escenario 1, pero sin reconectar todavía).
2. Reconecta el Wi-Fi para que arranque `sincronizarPendientes()`, y apenas veas en el log que empezó a enviar el lote, desconecta físicamente la alimentación del ESP32-CAM (no uses el botón de reinicio, debe ser un corte real).
3. Vuelve a alimentar el dispositivo y déjalo reconectar; debería reintentar la sincronización del mismo lote.
4. Revisa en la tabla `asistencias` del backend que los registros que sí llegaron a guardarse antes del corte no aparezcan duplicados.
5. Repite 2-3 veces, cortando en un punto distinto del envío cada vez, para tener más confianza en el resultado.

**Llenar:** columna "Corte durante sync" de la tabla `tab:estres_offline_fallas` ("Registros en el lote afectado", "Duplicados detectados tras reanudar", "Registros perdidos").

### 4.5 Escenario 5: Backend inaccesible con Wi-Fi activo
1. Deja el ESP32-CAM conectado normalmente a la red Wi-Fi (confirma en el menú embebido que el estado de red diga "EN LÍNEA").
2. Detén el proceso del backend Flask (`Ctrl+C` en la terminal donde corre, o apaga el contenedor si usas Docker Compose), sin tocar la red del dispositivo.
3. Realiza marcaciones (huella o rostro) y, con un cronómetro, mide cuánto tarda el dispositivo en dejar de esperar la respuesta del backend y guardar la marcación localmente en vez de quedarse colgado.
4. Verifica en `asistencias.json` (vía el menú de asistencias del dispositivo) que la marcación quedó guardada con `sincronizado=false`.
5. Reinicia el backend y verifica que la sincronización diferida recupere esas marcaciones sin pérdida.

**Llenar:** columna "Backend inaccesible" de la tabla `tab:estres_offline_fallas` ("Registros en el lote afectado", "Registros perdidos", "Tiempo hasta activar el guardado local").

> Objetivo específico 6 exige disponibilidad **≥ 90%** y objetivo específico 3 exige **0% de pérdida de datos**.

---

## 4.5. (Opcional) Estimación de consumo energético — sin multímetro

Esto respalda con números la afirmación de que el sensor PIR reduce el consumo del dispositivo, en la sección de "Análisis de sostenibilidad". Si tienes acceso a un multímetro o a un medidor de corriente USB (tipo "USB power meter", son baratos), mejor: mide el consumo real en mA en reposo y durante una captura activa, y salta directo al paso 4. Si no tienes ninguno, puedes estimarlo así:

1. Anota el consumo típico de cada componente según su hoja de datos (datasheet):
   - ESP32-CAM en operación activa (cámara + Wi-Fi transmitiendo): ~180-310 mA (varía según el módulo Wi-Fi y si el flash LED está encendido).
   - ESP32-CAM en reposo / deep-sleep (sin cámara ni flash activos): ~0.8-20 mA, dependiendo de si mantiene el Wi-Fi conectado o no.
   - AS608 durante una captura de huella: ~120 mA.
   - AS608 en reposo: bajo consumo, cercano a 0 cuando no está siendo consultado.
2. Estima cuánto tiempo al día el dispositivo está "activo" (capturando/transmitiendo) vs. "en espera". Por ejemplo, si esperas ~50 marcaciones al día y cada una toma ~5 segundos de actividad real, eso es 250 segundos activos sobre 86.400 segundos del día (~0.3% del tiempo).
3. Calcula el consumo promedio diario en dos escenarios:
   - **Sin PIR** (cámara y/o lector siempre en modo de espera activa, sin apagarse entre marcaciones): usa el consumo "activo" como base constante, o un valor intermedio si el firmware sin PIR igual hace polling.
   - **Con PIR** (lo que implementaste): el dispositivo está en su consumo de reposo la mayor parte del día, y solo sube al consumo activo durante el pequeño porcentaje de tiempo con presencia detectada.
4. Compara ambos escenarios (puedes expresarlo en mAh/día o como porcentaje de reducción) y usa ese número en la sección de sostenibilidad.

> Esto es una estimación analítica basada en datasheets, una técnica común en informática cuando no se dispone de instrumentación de hardware. Aclara en el informe que es una estimación y no una medición directa.

---

## 5. Orden sugerido de ejecución

1. **Costos** (5 min, solo juntar boletas) — hazlo primero, es lo más rápido.
2. **Pruebas de reconocimiento facial** (precisión + tiempos) — necesitas el sistema funcionando, hazlo cuando el prototipo esté estable.
3. **Pruebas de estrés offline** — el escenario 3 (reconexión prolongada) toma varios días, así que **inícialo lo antes posible** y haz el resto mientras corre en paralelo.
4. **Encuestas SUS** — déjalas para el final, después de que el sistema esté funcionando sin bugs evidentes (si la gente prueba un sistema con errores, el puntaje SUS sale artificialmente bajo y no refleja el diseño real).

---

## 6. Después de tener los datos

Una vez que tengas los números, dime los valores y yo los reemplazo directamente en las tablas de `memoria.tex` (los placeholders `\_\_\_\_`), recalculo el cumplimiento de cada objetivo específico en el capítulo de Conclusiones, y completo el "Análisis comparativo" de SUS con la interpretación real.
