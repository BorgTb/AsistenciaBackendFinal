# Preparación para la defensa — Preguntas críticas y cómo responderlas

Este documento reúne las preguntas que una comisión podría usar para cuestionar el proyecto,
agrupadas por tema. Cada pregunta incluye **por qué te la harían** (el flanco débil real) y
**una línea de defensa** basada en lo que ya está escrito en la memoria.

---

## 1. Metodología

### 1.1 ¿Por qué prototipado evolutivo incremental y no Scrum, XP o cascada?
**Por qué te lo preguntarán:** es la pregunta clásica; quieren ver si la elección fue razonada o por moda.

**Defensa:**
- El proyecto integra **hardware + firmware + backend + biometría**, con alto riesgo técnico en cada
  componente (¿el ESP32-CAM aguanta? ¿DeepFace funciona con esas imágenes?). El prototipado evolutivo
  permite validar la viabilidad técnica de cada pieza **antes** de comprometer la arquitectura completa.
- Cascada exige requisitos estables y congelados; aquí los requisitos hardware cambiaron durante el
  desarrollo (ej.: el sensor IR activo se reemplazó por PIR por falta de GPIO — Sección 6.3 de la memoria).
  Con cascada eso habría sido una falla de diseño; con prototipado fue una iteración normal.
- Scrum está pensado para **equipos** (roles: Scrum Master, Product Owner, dailies): trabajaste solo con
  el profesor guía como contraparte. Adoptar Scrum habría sido teatro de proceso. Sí tomaste lo útil:
  iteraciones con duración fija (3 semanas) y entregables funcionales validados al cierre de cada ciclo.
- Cada iteración cerró con pruebas funcionales documentadas (capítulo 4), que es exactamente lo que la
  metodología exige.

**Repregunta esperable:** *"¿Y en qué se diferencia entonces lo suyo de Scrum con otro nombre?"*
→ En prototipado evolutivo el artefacto que evoluciona es **el prototipo mismo** y la retroalimentación
viene de **pruebas técnicas**, no de un product owner priorizando un backlog de negocio. No hay
ceremonias ni roles, hay ciclos de requerimiento→diseño→implementación→validación.

### 1.2 Los pesos de las iteraciones (8%, 16%, 18%...) ¿de dónde salen?
**Flanco débil:** son estimaciones subjetivas; si dices que son "medidos" te hunden.

**Defensa:** admitirlo de frente: son **complejidad relativa estimada** en función de subsistemas
involucrados, riesgo técnico y volumen de pruebas (así está redactado en la Sección 3.2). No pretenden
ser una métrica objetiva de esfuerzo, sino una forma de comunicar avance ponderado en la carta Gantt.

### 1.3 ¿Cómo decidía cuándo una iteración estaba "terminada"?
**Defensa:** por la superación de las pruebas funcionales definidas al inicio de cada ciclo
(criterio de salida explícito por iteración, capítulo 4). No por sensación de avance.

---

## 2. Arquitectura

### 2.1 ¿Por qué el reconocimiento facial corre en el backend y no en el dispositivo?
**Por qué te lo preguntarán:** es LA decisión arquitectónica del proyecto, y tiene contras reales
(dependencia del servidor, imagen biométrica viajando por la red).

**Defensa:**
- El ESP32-CAM tiene ~520 KB de SRAM (+4 MB PSRAM): puede correr detección facial básica, pero **no**
  un modelo de embeddings como FaceNet con precisión >90% (Objetivo específico 2). El reconocimiento
  nativo del ESP32 es un juguete comparado con DeepFace.
- La arquitectura resultante es **híbrida borde-servidor deliberada**: el dispositivo hace captura,
  filtrado por PIR, almacenamiento offline y verificación de huella (que sí es local, en el AS608);
  el servidor hace la inferencia pesada. Lo reconoces explícitamente como límite en la Sección 5.6.
- La huella es justamente el **mecanismo de marcación que sigue funcionando sin backend**: la
  biometría no muere cuando se cae la red; muere solo la modalidad facial.

**Repregunta:** *"¿Y por qué no una Raspberry Pi, que sí corre el modelo localmente?"*
→ Costo y objetivo: una Raspberry Pi 4 + cámara + lector supera por sí sola el presupuesto de
$45.000 CLP del Objetivo 1 (el prototipo completo costó $34.000). Además el objetivo era demostrar
que se puede cumplir la norma con hardware de muy bajo costo; la proyección a ESP32-S3 (Sección 6.4)
es el camino de escalamiento sin romper esa premisa.

### 2.2 ¿Por qué HTTP **y** MQTT a la vez? ¿No es redundante?
**Defensa:** cumplen roles distintos y la elección es estándar en IoT:
- **HTTP** para transacciones petición-respuesta con payload grande (imagen JPEG → identificación,
  sincronización de lotes): el dispositivo necesita la respuesta síncrona ("¿quién es? ¿se guardó?").
- **MQTT** para lo que HTTP hace mal: comunicación **iniciada por el servidor** (comandos remotos,
  registrar huella, notificar cambios de personas/turnos), heartbeat liviano y detección inmediata de
  desconexión vía Last Will Testament. Con HTTP puro el backend tendría que hacer polling o el
  dispositivo mantener long-polling, mucho más caro en energía y red.

### 2.3 ¿Por qué Flask y no FastAPI, Django o Node/Express?
**Defensa razonada (no dogmática):**
- **Django** trae ORM, admin y plantillas que no se usan (el frontend es Next.js aparte): peso muerto.
- **FastAPI** habría sido una alternativa legítima (async, validación con Pydantic, OpenAPI). Flask se
  eligió por: madurez y documentación, integración directa y sin fricción con el ecosistema Python de
  visión (DeepFace, OpenCV, numpy corren en el mismo proceso), y porque la carga del sistema no es
  I/O-bound masiva (decenas de dispositivos, no miles de conexiones concurrentes) — el cuello de
  botella es la inferencia de DeepFace (410 ms), no el framework web.
- **Node** habría obligado a un servicio Python separado solo para DeepFace, agregando un salto de red
  y otro componente que mantener.
- Punto clave a decir: *"el framework web no es una decisión crítica de esta arquitectura; la decisión
  crítica es dónde corre la inferencia y cómo se sincroniza el modo offline. Flask es reemplazable por
  FastAPI en días sin tocar el resto del sistema."* Eso demuestra que entiendes qué decisiones importan.

### 2.4 ¿Por qué PostgreSQL y no MySQL/SQLite/Mongo?
**Defensa:**
- Los datos son **fuertemente relacionales** (empresa→personas→asistencias→turnos→dispositivos) y el
  aislamiento multi-tenant se apoya en integridad referencial y filtros por `empresa_id`: un documental
  (Mongo) no aporta nada aquí y complica los joins de reportes.
- SQLite no soporta bien escritura concurrente de múltiples orígenes (N dispositivos + panel web + sync).
- PostgreSQL vs MySQL: prestaciones equivalentes para este caso; PostgreSQL es open source sin ambigüedad
  de licencia (coherente con el objetivo de sistema abierto), y su manejo de JSON permite guardar
  payloads flexibles (field_map de integraciones ERP).

### 2.5 ¿El multi-tenant por filtro `empresa_id` no es frágil? ¿Por qué no una BD por empresa?
**Flanco débil real:** un `WHERE empresa_id = ...` olvidado en una consulta filtra datos entre empresas.

**Defensa:** es el modelo **shared database / shared schema**, el estándar de la industria para SaaS
pequeño-mediano (menor costo operativo, migraciones únicas). Los mitigantes: el filtro se aplica en
decoradores/capa de autorización centralizada (JWT trae `empresa_id`), y las pruebas de caja negra
incluyen explícitamente casos de acceso cruzado entre empresas. Una BD por empresa sería el paso natural
si el producto escalara a clientes que exigen aislamiento físico — se menciona como evolución, no se
implementa porque el objetivo era el prototipo.

---

## 3. Elección de tecnologías biométricas

### 3.1 ¿Por qué FaceNet y no ArcFace u otro modelo más nuevo?
**Defensa (ya está en la memoria, úsala):** FaceNet (128 dimensiones) fue el modelo **más liviano que
cumple el umbral de precisión del Objetivo 2** (>90%). ArcFace da 1-2 puntos más de acierto a costo de
embeddings de 512 dimensiones y más cómputo por inferencia: en un backend que puede correr en hardware
modesto, ese costo marginal no se justifica (argumento de Green AI, Sección 5.6, con cita a Schwartz
et al. y Strubell et al.).

### 3.2 ¿Cómo eligió el umbral de distancia euclidiana de 10.0? ¿Hizo una curva ROC?
**Flanco débil real:** no hay curva ROC/DET ni calibración formal FAR-FRR en la memoria.

**Defensa honesta:**
- 10.0 es el umbral de referencia de DeepFace para FaceNet con distancia euclidiana (valor validado por
  la librería sobre datasets estándar como LFW), y se **verificó empíricamente** sobre el conjunto
  propio: con ese umbral se obtuvo TPR 95% y FPR 2% (Tabla de precisión, Sección 5.3).
- Admitir: una calibración ROC propia con un dataset mayor es trabajo futuro legítimo; con 20 ciclos de
  identificación y 50 pruebas de impostor el tamaño muestral no da para una curva estable.
- Señalar que el umbral es **configurable** (`FACIAL_UMBRAL_DISTANCIA`), es decir, la arquitectura ya
  permite recalibrar sin tocar código.

### 3.3 El anti-spoofing es solo software. ¿Un video en un teléfono lo engaña?
**Defensa:** está reconocido como limitación explícita (Sección 6.3): el anti-spoofing de DeepFace más
la validación de nitidez (varianza Laplaciana) rechazó 14/15 ataques con fotografía/pantalla (93.3%),
suficiente contra el ataque *realista* en una pyme (un compañero marcando con una foto). Contra ataques
sofisticados (máscaras 3D, video de alta calidad) se propone sensor de profundidad (VL53L5CX sobre
ESP32-S3) como proyección. Además hay una segunda capa: el PIR exige presencia física real frente al
dispositivo, y toda identificación queda en `logs_biometricos` con auditoría — el fraude deja rastro.

---

## 4. Calidad de implementación ("¿está bien hecho?")

### 4.1 ¿Cómo demuestra que el sistema está bien construido y no solo que "funciona en la demo"?
**Defensa — enumerar las capas de verificación que existen:**
1. **Pruebas unitarias automatizadas** con mocks (DeepFace, MQTT, SMTP, BD): lógica de negocio,
   cifrado, control de acceso por rol, robustez ante fallos (Sección 3.3.5). Ejecutables en cualquier
   entorno sin hardware.
2. **Pruebas de caja negra sobre los 28 endpoints**: códigos HTTP, estructura JSON, autenticación y
   autorización por rol, casos de error (Sección 3.3.4).
3. **Pruebas de integración ascendente** por iteración: hardware→almacenamiento→backend→BD→web.
4. **Pruebas de estrés offline en 5 escenarios**, incluyendo corte de energía en mitad de una
   sincronización (0 duplicados, 0 pérdidas) y backend caído con Wi-Fi activo.
5. **Idempotencia por diseño**: el endpoint de asistencias detecta duplicados (misma persona+tipo+día)
   y devuelve el id existente — la corrección no depende de que la red se porte bien.

**Ten a mano:** el % de cobertura de la suite (hay carpeta `htmlcov` en el repo — ejecuta
`pytest --cov` antes de la defensa y memoriza el número). Si preguntan y no lo sabes, se ve mal.

### 4.2 Los embeddings van cifrados (Fernet), pero ¿y las fotos crudas?
**Flanco débil real:** las capturas se guardan como JPG en `static/previews/` y
`static/capturas_prueba/` **sin cifrar**. Es dato biométrico sensible en claro en disco. Si un miembro
de la comisión leyó el detalle, te lo va a sacar.

**Defensa:** no lo niegues. Línea: el dato biométrico *operativo* (el embedding, que es lo que permite
identificar) está cifrado en reposo con Fernet; las imágenes se retienen como evidencia de auditoría
de cada marcación. Cifrarlas en reposo (o retenerlas solo N días) es una mejora directa y de bajo
costo que reconoces como pendiente. **Mejor aún: implementa una política de retención/cifrado antes de
la defensa si hay tiempo, y entonces la respuesta es "ya está resuelto así".**

### 4.3 El fallback `X-Device-MAC` para dispositivos sin JWT ¿no es suplantable?
**Flanco débil real:** una cabecera MAC es trivialmente falsificable; alguien en la LAN podría inyectar
marcaciones si conoce la MAC de un dispositivo enrolado.

**Defensa:** el enrolamiento requiere PIN generado por un admin (la MAC sola no enrola), el dispositivo
puede tener contraseña propia (SHA-256), y en modo producción el canal va sobre TLS con autenticación
MQTT. Admitir que mover los dispositivos a un token propio por dispositivo (mTLS o JWT de dispositivo)
es el endurecimiento natural para producción. Enmarcarlo como decisión consciente de prototipo:
la prioridad fue validar el flujo completo; la superficie de ataque queda documentada.

### 4.4 ¿Por qué JWT de 24 horas? ¿HS256 y no RS256?
**Defensa:** un solo emisor y un solo consumidor del token (el propio backend) → HS256 es apropiado;
RS256 se justifica cuando terceros deben verificar tokens sin poder emitirlos. 24 h equilibra fricción
de uso en una pyme vs. exposición; es un parámetro (`JWT_EXP_HOURS`), no una constante — bajarlo es
configuración, no desarrollo.

---

## 5. Confiabilidad del producto y validez de las mediciones (la parte más atacable)

### 5.1 "95% de precisión"... con n=20. ¿Eso es estadísticamente serio?
**Por qué te lo preguntarán:** 19/20 aciertos da un intervalo de confianza enorme (IC 95% aprox.
75%–100%). Un profesor con formación en estadística lo va a ver al instante. Lo mismo con
anti-spoofing 14/15 y falsos positivos 1/50.

**Defensa (la única viable es la honesta):**
- Los objetivos específicos definieron **criterios de aceptación de ingeniería para un prototipo en
  laboratorio**, no una validación estadística de un producto biométrico comercial. El umbral ">90% en
  pruebas de laboratorio" está redactado así en el Objetivo 2 desde el capítulo 1: se midió exactamente
  lo comprometido.
- Los tamaños muestrales son los alcanzables por un equipo de una persona sin acceso a un panel amplio
  de sujetos (limitación declarada en Sección 6.3).
- La validación a escala (más sujetos, más condiciones, curva ROC, operación de semanas) está
  explícitamente en proyecciones futuras.
- **Prepárate para decir cuántas personas distintas** componían el set de pruebas facial (no solo
  cuántos intentos). Si fueron 2-3 personas, dilo antes de que te lo saquen; si fueron más, mejor.

**No hagas:** defender el 95% como si fuera una cifra generalizable. En cuanto digas "el sistema tiene
95% de precisión" a secas, te preguntarán por el intervalo de confianza y pierdes.

### 5.2 En conectividad intermitente sincronizó 29 de 31 (93.5%). ¿Dónde están los otros 2 registros? ¿No dice la Resolución 38 que no puede haber pérdida?
**Flanco débil serio:** si esos 2 registros se **perdieron**, contradice el discurso de "sin pérdida de
datos" y el requisito normativo. Tienes que saber la respuesta exacta antes de la defensa.

**Preparación obligatoria:** revisa el log de esa prueba y determina qué pasó con los 2 registros:
- Si quedaron en el dispositivo pendientes de sincronizar (no perdidos, solo tardíos) → la métrica es
  "sincronizados dentro de la ventana de la prueba" y la defensa es limpia: 0 pérdida, 2 rezagados.
- Si efectivamente se perdieron (ej.: corte en medio de la escritura en flash) → identifica la causa y
  preséntala como hallazgo de la prueba (para eso son las pruebas de estrés) + mitigación propuesta.
- La conclusión (Objetivo 6) usa un umbral de disponibilidad ≥90% que absorbe este resultado, pero la
  comisión puede contrastarlo con el Objetivo 5 que promete "100% de los paquetes" — ten clara la
  distinción: el 100% se verificó en el escenario de desconexión total y reconexión prolongada
  (24/24 y 147/147); el 93.5% corresponde al escenario intermitente, medido dentro de la ventana de
  observación.

### 5.3 El Objetivo 3 (1.000 registros offline) quedó "cumplido parcialmente". ¿No es un objetivo fallido?
**Defensa (ya está bien planteada en la memoria, refuérzala):**
- La falla no es de concepto sino de **dimensionamiento de hardware**: el límite es el buffer JSON de
  32 KB en RAM, no la flash. Detectarlo, explicarlo técnicamente y proponer tres soluciones concretas
  (ESP32-S3, microSD por SPI, sincronización más frecuente) demuestra más dominio que un "cumplido"
  sin análisis.
- En condiciones de operación realistas (el dispositivo sincroniza cada vez que hay red), el límite
  práctico no se alcanza: 147 registros acumulados en el peor escenario probado, sin pérdida.
- Frase útil: *"preferí reportarlo como cumplimiento parcial con causa raíz identificada antes que
  declararlo cumplido apoyándome en que la prueba de 147 registros pasó"*. La honestidad metodológica
  suma puntos en una defensa.

### 5.4 ¿Cómo sé que las pruebas SUS valen algo con n=6 y n=3?
**Flanco débil real:** n=9 total; además probable sesgo de selección (¿conocidos tuyos?).

**Defensa:**
- SUS es un instrumento **estandarizado y validado** (Brooke 1996); usarlo con muestras pequeñas es
  práctica aceptada para evaluación formativa de prototipos (la literatura de usabilidad — Nielsen —
  sostiene que 5 usuarios detectan la mayoría de los problemas de usabilidad).
- El objetivo (SUS ≥ 68) se definió a priori en el capítulo 1 y ambos grupos lo superaron con margen
  (89.6 y 82.5): incluso con el error propio de una muestra pequeña, la distancia al umbral es grande.
- No afirmas significancia estadística en la memoria (no hay test de hipótesis sobre la diferencia
  de 7.1 puntos — se presenta como observación descriptiva). Mantén esa disciplina al hablar.
- Ojo con el detalle: en la memoria conviven "≥68" (objetivo) y "≥70 aceptable según Bangor". Si te lo
  sacan: 68 es el promedio histórico de SUS (percentil 50) y 70 el corte "aceptable" de Bangor; tu
  resultado supera ambos, así que la discrepancia no afecta la conclusión.

### 5.5 ¿Cómo mediste los tiempos (685 ms)? ¿Con qué carga? ¿Cuántas personas en la BD?
**Preparación obligatoria:** ten memorizado el protocolo de medición: 20 ciclos, condiciones de
laboratorio, cómo se cronometró (¿timestamps en el firmware? ¿logs del backend?), cuántos embeddings
había en la BD al medir (el 1:N escala lineal con el número de personas — si medste con 5 personas,
con 500 el tiempo de comparación crece, aunque la parte dominante es la inferencia, que es constante).
Si no puedes responder "cómo se midió", el número pierde credibilidad completa.

---

## 6. Utilidad, normativa y producto

### 6.1 ¿Esto realmente cumple la Resolución Exenta N°38? ¿Verificó requisito por requisito?
**Por qué es peligrosa:** la memoria dice "conforme a la Resolución Exenta N°38" en las conclusiones.
Si un comisionado abre la resolución y te pregunta por un artículo concreto (inalterabilidad de los
registros, comprobante de marcación para el trabajador, disponibilidad para fiscalización, geolocalización
en casos aplicables), necesitas respuesta.

**Preparación obligatoria:** arma una tabla requisito→cómo lo cubre el sistema→qué queda fuera.
Puntos fuertes que ya tienes: registro biométrico con verificación de identidad, trazabilidad completa
(logs de auditoría), no pérdida ante desconexión, timestamps, consentimiento. Puntos a revisar
honestamente: ¿los registros de asistencia son inalterables (no hay endpoint de edición/borrado de
marcaciones)? ¿el trabajador recibe comprobante de cada marcación (el email cumple ese rol si está
configurado)? ¿reportes en el formato que exige la DT? La respuesta madura es: *"el prototipo implementa
los requisitos técnicos centrales (X, Y, Z); la certificación formal ante la DT exige además A y B, que
están en proyecciones"*. Nunca digas "cumple la norma" a secas si no hiciste el checklist.

### 6.2 Ley de protección de datos (19.628 / 21.719): la biometría es dato sensible. ¿Basta el consentimiento?
**Defensa:** el sistema implementa las tres obligaciones clave: **consentimiento previo** registrado
(tabla `consentimientos`, sin consentimiento el registro facial devuelve 403), **derecho de supresión**
(eliminación de datos biométricos con auditoría en `eliminaciones_biometricas`, limpieza de RUT/email)
y **seguridad del dato** (cifrado en reposo del embedding, TLS en tránsito, control de acceso por rol).
Conoce la Ley 21.719 (nueva ley de datos personales chilena, en vigencia gradual): que te escuchen
nombrarla suma; reconoce que una implementación productiva requeriría evaluación de impacto (DPIA).

### 6.3 ¿Quién usaría esto pudiendo comprar un reloj control certificado por ~$100.000?
**Defensa (es tu propuesta de valor, tenla afilada):**
1. Los comerciales baratos no se integran con ERP (formatos cerrados, CSV manual) — el tuyo expone API
   REST + webhooks con field-mapping configurable.
2. Requieren internet permanente o pierden marcaciones — el tuyo opera offline con sincronización
   diferida verificada.
3. Costo: $34.000 en hardware vs. dispositivos comerciales + licencias SaaS mensuales por trabajador.
4. Es código abierto y modular: una pyme o un integrador puede adaptarlo (turnos, antifraude,
   multi-empresa) sin depender del proveedor.
- Y la concesión honesta: no compite hoy con soluciones certificadas en madurez ni soporte; es la
  demostración de que la alternativa abierta es técnicamente viable.

### 6.4 ¿Probaste la integración ERP contra un ERP real o contra un mock?
**Preparación:** en el repo hay `odoo-test/` y `odoo_addons/` — si la probaste contra Odoo, dilo con
orgullo (es un ERP real y open source, coherente con el proyecto); ten el flujo demo listo. Si solo
fue contra un webhook simulado, di que el mecanismo (webhook + field mapping) es agnóstico del ERP y
que la prueba con Odoo/mock validó el contrato de datos.

---

## 7. Preguntas incómodas de cierre (y la actitud correcta)

| Pregunta | Respuesta en una línea |
|---|---|
| "¿Qué es lo más débil de su proyecto?" | El tamaño muestral de las validaciones (biometría y SUS) y el buffer RAM del almacenamiento offline; ambos identificados, con causa raíz y plan de mejora. Nombrar tus debilidades tú mismo transmite dominio. |
| "¿Qué haría distinto si empezara de nuevo?" | Elegir ESP32-S3 desde el inicio (RAM/flash) y definir el protocolo de medición estadística de la biometría en el capítulo de metodología, con más sujetos. |
| "¿Esto es un producto o un prototipo?" | Prototipo funcional que valida viabilidad técnica y normativa; la memoria nunca afirma ser producto (los términos están cuidados en todo el texto). |
| "¿Por qué debería aprobar este trabajo?" | Integra hardware, firmware, backend, biometría, seguridad y normativa en un sistema completo y medido, con 8 iteraciones documentadas, suite de pruebas en 4 niveles y resultados contrastados objetivo por objetivo, incluyendo los que no se cumplieron del todo. |

---

## 8. Checklist antes de la defensa (cosas que DEBES saber de memoria)

- [ ] Número de cobertura de la suite de pruebas (`pytest --cov`) y cantidad de tests.
- [ ] Cuántas **personas distintas** participaron en las pruebas de reconocimiento facial y cuántos embeddings había en la BD al medir tiempos.
- [ ] Qué pasó exactamente con los **2 registros no sincronizados** del escenario intermitente (¿rezagados o perdidos?).
- [ ] Los 6 objetivos específicos con sus umbrales numéricos y el resultado obtenido de cada uno (45.000→34.000; <5 s→685 ms; 1.000 reg→parcial por buffer 32 KB; SUS 68→89.6/82.5; sync 100%→100/93.5/100; disponibilidad 90%→93.5%).
- [ ] Los 3-4 artículos clave de la Resolución 38 y cómo los cubre (o no) el sistema.
- [ ] Por qué MTCNN sobre RetinaFace (145 ms vs 410 ms, −1.5 pts de acierto) y por qué FaceNet sobre ArcFace.
- [ ] El flujo completo de una marcación de memoria: PIR → captura → validación de nitidez → embedding → comparación 1:N contra caché → registro idempotente → push ERP async → email.
- [ ] Perfil de quién te evalúa: si hay alguien de datos/estadística, espera ataque por n; si hay alguien de seguridad, espera ataque por X-Device-MAC y fotos sin cifrar; si hay alguien de ingeniería de software, espera ataque por metodología y cobertura.

## 9. Mejoras de bajo costo que puedes hacer ANTES de la defensa (convierten flancos en fortalezas)

1. **Cifrar o purgar las imágenes de `static/previews/` y `static/capturas_prueba/`** (política de retención). Cierra la pregunta 4.2.
2. Correr `pytest --cov` y anotar el número en tus notas (y si es decente, en una lámina).
3. Hacer el **checklist Resolución 38 requisito-por-requisito** (una tabla de una página).
4. Verificar en los logs qué pasó con los 2 registros del escenario intermitente.
5. Confirmar que **no existe endpoint de edición/borrado de asistencias** (inalterabilidad); si existe, restringirlo o justificarlo.
