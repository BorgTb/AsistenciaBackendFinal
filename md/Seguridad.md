Bloque 1 — Seguridad y legalidad biométrica
Tarea 1.1 — Consentimiento documentado
Crear tabla consentimientos en PostgreSQL con campos: persona_id, fecha_aceptacion, version_politica, ip_dispositivo, metodo_aceptacion. Modificar el flujo de enrolamiento en facial.py para que verifique existencia de consentimiento antes de permitir registro biométrico. Si no existe consentimiento, retornar error 403 con mensaje claro.

Tarea 1.3 — Cifrado de embeddings
Implementar cifrado simétrico AES sobre el embedding antes de guardarlo en BD. La clave debe venir de variable de entorno BIOMETRIC_KEY. Descifrar al momento de leer para comparación. Agregar migración para cifrar embeddings existentes.
Tarea 1.4 — Log de acceso biométrico
Crear tabla logs_biometricos con campos: persona_id, dispositivo_id, timestamp, tipo_operacion (identificacion/verificacion/registro/eliminacion), resultado, ip_origen. Insertar registro en cada operación que use un embedding.
Tarea 1.5 — Derecho al olvido
Crear endpoint DELETE /api/personas/<id>/datos-biometricos que elimine el embedding, las fotos físicas si existen, e inserte un registro en tabla eliminaciones_biometricas con timestamp y usuario que solicitó la eliminación. El registro de asistencias se mantiene pero disociado del dato biométrico.