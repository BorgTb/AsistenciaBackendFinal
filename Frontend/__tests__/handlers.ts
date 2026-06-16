import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

export const server = setupServer(
  http.post('/api/auth/login', () =>
    HttpResponse.json({
      ok: true,
      token: 'fake-jwt-token-abc123',
      user: {
        id: 1,
        nombre: 'Admin Test',
        email: 'admin@empresa.cl',
        rol: 'admin',
        empresa_id: 1,
        empresa_nombre: 'Empresa por defecto'
      }
    })
  ),
  http.get('/api/auth/me', () =>
    HttpResponse.json({
      user: {
        id: 1,
        nombre: 'Admin Test',
        email: 'admin@empresa.cl',
        rol: 'admin',
        empresa_id: 1,
        empresa_nombre: 'Empresa por defecto'
      }
    })
  ),
  http.get('/api/personas', () =>
    HttpResponse.json([
      { id: '1', nombre: 'Juan', rut: '11.111.111-1', email: 'juan@test.cl',
        huella_id: 0, empresa_id: 1, fecha_registro: '2026-01-01', sincronizado: true }
    ])
  ),
  http.post('/api/personas', () =>
    HttpResponse.json({ ok: true, id: '2' })
  ),
  http.get('/api/turnos', () =>
    HttpResponse.json([
      { id: '1', nombre: 'Turno A', inicio: '08:00', fin: '17:00', dias: 'L,M,X,J,V', empresa_id: 1 }
    ])
  ),
  http.get('/api/asistencias', () =>
    HttpResponse.json([
      { id: '1', persona_id: '1', nombre: 'Juan', tipo: 'entrada', metodo: 'facial',
        fecha_hora: '2026-01-01T08:00:00', origen: 'dispositivo', sincronizado: true, dispositivo_id: 1 }
    ])
  ),
  http.get('/api/dispositivos', () =>
    HttpResponse.json([])
  ),
  http.get('/api/erp', () =>
    HttpResponse.json([])
  ),
  http.get('/api/auth/usuarios', () =>
    HttpResponse.json([
      { id: 1, nombre: 'Admin', email: 'admin@empresa.cl', rol: 'admin',
        activo: true, created_at: '2026-01-01', empresa_nombre: 'Empresa por defecto', empresa_id: 1 }
    ])
  ),
  http.get('/api/auth/empresas', () =>
    HttpResponse.json([
      { id: 1, nombre: 'Empresa por defecto', rut_empresa: '00000000-0',
        email_contacto: '', telefono: '', direccion: '', created_at: '2026-01-01' }
    ])
  ),
  http.post('/api/dispositivos/:id/generar-password', ({ params }) =>
    HttpResponse.json({ ok: true, password: 'Ab3Xyz9KmL2p' })
  ),
  http.delete('/api/dispositivos/:id/password', () =>
    HttpResponse.json({ ok: true, mensaje: 'Contrasena eliminada' })
  )
);
