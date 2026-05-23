# Lógica de Roles y Autenticación — Sistema SAS

## Roles

| Rol | Alcance | Restricción principal |
|---|---|---|
| `admin` | Todo el sistema | Ninguna |
| `empleador` | Solo su empresa | Filtrado por `empresa_id` |
| `trabajador` | Solo sus datos | Filtrado por `persona_id` |

---

---



---

## Flujo de enrolamiento de dispositivo

```
1. Admin crea empresa + usuario empleador en el sistema
2. Empleador entra al panel → "Agregar dispositivo"
3. Backend genera PIN de 8 chars aleatorio
4. Inserta en dispositivos: (empresa_id, codigo_enrol, enrolado=FALSE)
5. Empleador toma el dispositivo físico
6. Entra a http://192.168.4.1/wifi-setup
7. Configura: SSID, contraseña WiFi, URL del backend, PIN
8. ESP32 hace POST /api/dispositivos/enrolar con { codigo, mac, ip }
9. Backend valida:
   - ¿Existe el código?
   - ¿Pertenece a la empresa del token?
   - ¿No está ya enrolado?
10. Si válido: UPDATE dispositivos SET enrolado=TRUE, mac=..., ip=..., codigo_enrol=NULL
11. ESP32 recibe OK → queda vinculado
12. Todos los marcajes del ESP32 llevan empresa_id de ese dispositivo
```

---

## Lógica de filtrado — regla general

Todo query que devuelve datos sensibles debe aplicar este filtro según el rol del token:

```
si rol == 'admin':
    sin filtro adicional

si rol == 'empleador':
    AND empresa_id = token.empresa_id

si rol == 'trabajador':
    AND empresa_id = token.empresa_id
    AND persona_id = token.persona_id
```

El filtro se aplica en el backend, nunca en el frontend. El cliente no puede modificar su propio token.

---

## Decoradores necesarios (Flask)

Tres decoradores cubren todos los casos:

- `@requiere_login` → verifica que el token sea válido y no haya expirado
- `@requiere_rol('admin', 'empleador')` → restringe por rol, acepta lista de roles permitidos
- `@solo_mis_datos` → para endpoints de trabajador, verifica que persona_id coincida

---

## Vistas por rol — qué ve cada uno en el panel web

### Admin
- Dashboard global con todas las empresas
- Lista de empresas y empleadores
- Todos los dispositivos del sistema
- Todos los marcajes
- Logs del sistema
- Gestión de integraciones ERP

### Empleador
- Dashboard de su empresa
- Sus dispositivos (con estado online/offline)
- Sus trabajadores (registro, turnos, asignaciones)
- Marcajes de su empresa
- Configuración de integración ERP
- Exportar reportes

### Trabajador
- Sus propias asistencias del mes
- Su turno asignado
- Resumen de horas
- Sin acceso a datos de otros trabajadores
- Sin acceso a dispositivos ni configuración

El flujo exacto que debería seguir un empleador cuando compra el dispositivo es este:
Primero el admin crea la empresa y el usuario empleador desde el panel. Segundo el empleador entra a su panel y hace clic en "Agregar dispositivo", el sistema genera un PIN de 8 caracteres aleatorio y lo guarda en la tabla dispositivos con enrolado = FALSE. Tercero el empleador toma el dispositivo físico, entra a 192.168.4.1/wifi-setup, configura el WiFi de la empresa y en un campo adicional ingresa la URL del backend y el PIN. Cuarto el ESP32 hace POST a /api/dispositivos/enrolar con el PIN, su MAC y su IP local. El backend valida, vincula el dispositivo a la empresa y retorna OK. Desde ese momento el dispositivo queda asociado a esa empresa y todos sus marcajes se guardan con ese empresa_id.