# SAS Next — Frontend

**Sistema de Asistencia (SAS)** — Aplicación web para la gestión de asistencia laboral con soporte para dispositivos IoT (huella dactilar y reconocimiento facial), integración ERP y multiempresa.

---

## Stack Tecnológico

| Tecnología | Versión | Propósito |
|---|---|---|
| Next.js | ^16.2.6 | Framework React con App Router |
| React | 19.0.0 | Librería UI |
| TypeScript | ^5 | Tipado estático |
| CSS personalizado | — | Sistema de diseño propio (dark theme, sin frameworks) |

---

## Estructura del Proyecto

```
Frontend/
├── app/                        # App Router (páginas + API routes)
│   ├── globals.css             # Sistema de diseño completo (1229 líneas)
│   ├── layout.tsx              # Layout raíz (AuthProvider, fuentes)
│   ├── page.tsx                # Dashboard principal (/)
│   ├── login/page.tsx          # Login (/login)
│   ├── asignaciones/page.tsx   # Asignaciones persona-turno
│   ├── asistencias/page.tsx    # Registro de asistencias
│   ├── dispositivos/page.tsx   # Gestión de dispositivos IoT
│   ├── empresas/page.tsx       # Administración de empresas
│   ├── erp/page.tsx            # Integraciones ERP
│   ├── logs/page.tsx           # Visor de logs del sistema
│   ├── personas/page.tsx       # Gestión de personas/empleados
│   ├── turnos/page.tsx         # Gestión de turnos
│   ├── usuarios/page.tsx       # Administración de usuarios
│   └── api/                    # Proxy API hacia backend Flask
├── components/                 # Componentes React
│   ├── LoginForm.tsx           # Formulario de inicio de sesión
│   ├── RequireAuth.tsx         # Guardia de autenticación
│   └── SasDashboard.tsx        # Dashboard SPA completo (2110 líneas)
├── lib/                        # Módulos de utilidad
│   ├── api.ts                  # Cliente API genérico
│   ├── auth-api.ts             # Cliente API de autenticación
│   ├── auth-context.tsx        # Contexto global de autenticación
│   ├── auth-types.ts           # Interfaces de autenticación
│   └── types.ts                # Interfaces del modelo de datos
├── middleware.ts               # Middleware de redirección por auth
├── next.config.mjs             # Configuración Next.js
├── Dockerfile                  # Build multi-etapa para producción
├── tsconfig.json               # Configuración TypeScript
└── package.json                # Dependencias y scripts
```

---

## Funcionalidades por Módulo

### 1. Autenticación (`/login`)
- Inicio de sesión con email y contraseña
- Selección de empresa si el usuario pertenece a múltiples empresas
- JWT almacenado en `localStorage` y cookie (`sas_token`)
- Middleware que protege todas las rutas excepto `/login` y `/api/auth`
- Roles: `admin` (super administrador), `empleador` (empleador/gestor), `trabajador` (trabajador)

### 2. Dashboard (`/`)
- **Métricas principales**: marcajes hoy, total personas, total dispositivos, dispositivos con facial+huella
- **Panel de estado**: resumen del sistema
- **Acciones rápidas**: botones para registrar persona, crear turno, asignar turno, verificar dispositivos
- **Tabla de asistencias recientes**: últimas 5 asistencias registradas

### 3. Personas (`/personas`)
- Listado de personas/empleados con RUT, nombre, email
- Indicador visual de estado de huella dactilar
- Crear, editar y eliminar (desactivar) personas
- Registro de foto para reconocimiento facial (subida de imagen)
- Asignación de ID de huella dactilar

### 4. Turnos (`/turnos`)
- Creación de turnos con nombre, hora de inicio y fin
- Selección de días activos (lunes a domingo)
- Eliminación de turnos

### 5. Asignaciones (`/asignaciones`)
- Asignación de personas a turnos
- Listado de asignaciones vigentes con persona y turno asociados
- Eliminación de asignaciones

### 6. Asistencias (`/asistencias`)
- Tabla filtrable por fecha, tipo (entrada/salida) y método
- Indicador visual de sincronización con ERP
- Exportación a CSV
- Sincronización manual de registros

### 7. Dispositivos (`/dispositivos`)
- Tarjetas visuales con estado online/offline
- Generación de PIN de enrolamiento para dispositivos biométricos
- Verificación de conectividad
- Renombrar y eliminar dispositivos

### 8. ERP (`/erp`)
- Integración con sistemas ERP (Odoo, Defontana, Buk, SAP)
- Configuración por webhook con headers personalizados y mapeo de campos
- Prueba de conexión, envío manual de datos
- Visualización de estado de la integración
- Presets para Odoo, Defontana, Buk y SAP con configuraciones predefinidas

### 9. Empresas (`/empresas`) — Solo admin
- Creación y eliminación de empresas
- Asignación de usuarios a empresas con roles específicos
- Gestión multiempresa

### 10. Usuarios (`/usuarios`)
- Listado de usuarios del sistema
- Creación de nuevos usuarios
- Cambio de contraseña
- Eliminación de usuarios

### 11. Logs (`/logs`)
- Visor de logs del sistema con filtro por tipo (ok, err, info, warn)
- Limpieza de logs

---

## Arquitectura

### Patrón de Comunicación
```
Navegador → Next.js API Route (proxy) → Flask Backend → Base de Datos
```

Todas las llamadas API pasan por rutas Next.js que actúan como proxy (`app/api/_proxy.ts`), reenviando las peticiones al backend Flask configurado en `FLASK_API_BASE_URL`. Esto evita problemas de CORS y permite manejar la autenticación centralizadamente.

### Estado Global
- **AuthContext**: Único contexto global, maneja usuario autenticado y token JWT
- **Dashboard State**: Estado local en `SasDashboard.tsx` mediante `useState` hooks
- No se utilizan librerías externas de estado (Redux, Zustand, etc.)

### Navegación SPA
Todas las páginas autenticadas renderizan el mismo componente `SasDashboard` con distintos `initialSection`, creando una experiencia tipo SPA sin recargas completas de página.

### Diseño Visual
- Tema oscuro con propiedades CSS personalizadas
- Sistema de cuadrícula responsivo (breakpoints: 1500px, 1120px, 720px)
- Componentes: botones, badges, paneles, tarjetas, modales, tablas, grids
- Animaciones de pulso para indicadores en vivo
- Notificaciones toast auto-dismiss (3.2s)

---

## Variables de Entorno

| Variable | Valor por defecto | Propósito |
|---|---|---|
| `FLASK_API_BASE_URL` | `http://127.0.0.1:5000` | URL del backend Flask (server-side) |
| `NEXT_PUBLIC_DEVICE_BASE_URL` | `http://192.168.4.1` | URL base para dispositivos ESP32 (client-side) |

---

## Scripts Disponibles

```bash
npm run dev      # Inicia servidor de desarrollo
npm run build    # Compila para producción
npm run start    # Inicia servidor de producción (requiere build previo)
```

---

## Despliegue con Docker

```bash
docker build -t sas-frontend .
docker run -p 3000:3000 sas-frontend
```

El `Dockerfile` usa build multi-etapa con `node:22-alpine` y `output: 'standalone'` para producir una imagen optimizada.

---

## Dependencias

**Producción:**
- `next` ^16.2.6
- `react` ^19.0.0
- `react-dom` ^19.0.0

**Desarrollo:**
- `@types/node` ^22
- `@types/react` ^19
- `@types/react-dom` ^19
- `typescript` ^5

---

## Notas Técnicas

- **Sin Server Components**: Todas las páginas usan `'use client'`, no hay React Server Components.
- **Sin framework CSS**: El diseño es 100% CSS personalizado, sin Tailwind, Bootstrap ni similares.
- **Sin base de datos**: El frontend solo hace peticiones HTTP; toda la lógica de negocio y persistencia está en el backend Flask.
- **Proxy API**: Las rutas `app/api/*` son thin handlers que delegan al backend Flask mediante `proxyJsonRequest`.
