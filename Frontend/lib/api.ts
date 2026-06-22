import type { Asignacion, Asistencia, ErpIntegration, Persona, Turno } from '@/lib/types';

const baseUrl = '';

async function request<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers || {})
      },
      cache: 'no-store'
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function getPersonas() {
  return request<Persona[]>('/api/personas');
}

export async function createPersona(payload: { nombre: string; rut: string; email?: string }) {
  return request<{ ok: boolean; id: string } | { error: string }>('/api/personas', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function deletePersona(personaId: string) {
  return request<{ ok: boolean } | { error: string }>(`/api/personas/${personaId}`, {
    method: 'DELETE'
  });
}

export async function getPersonaById(personaId: number) {
  return request<{ id: string; nombre: string; rut: string; email: string; huella_id: number; encoding_facial: string | null; fecha_registro: string; activo: boolean } | { error: string }>(`/api/personas/${personaId}`);
}

export async function registrarConsentimiento(personaId: number, version?: string, metodo?: string) {
  return request<{ ok: boolean; mensaje: string } | { error: string }>(`/api/personas/${personaId}/consentimiento`, {
    method: 'POST',
    body: JSON.stringify({
      version_politica: version || '1.0',
      metodo_aceptacion: metodo || 'web'
    })
  });
}

export async function eliminarDatosBiometricos(personaId: number) {
  return request<{ ok: boolean; mensaje: string } | { error: string }>(`/api/personas/${personaId}/datos-biometricos`, {
    method: 'DELETE'
  });
}

export async function getTurnos() {
  return request<Turno[]>('/api/turnos');
}

export async function createTurno(payload: { nombre: string; inicio: string; fin: string; dias: string }) {
  return request<{ ok: boolean; id: string } | { error: string }>('/api/turnos', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function deleteTurno(turnoId: string) {
  return request<{ ok: boolean } | { error: string }>(`/api/turnos/${turnoId}`, {
    method: 'DELETE'
  });
}

export async function getAsignaciones() {
  return request<Asignacion[]>('/api/asignaciones');
}

export async function createAsignacion(payload: { rut: string; turno_id: string }) {
  return request<{ ok: boolean; id: string } | { error: string }>('/api/asignaciones', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function deleteAsignacion(asignacionId: string) {
  return request<{ ok: boolean } | { error: string }>(`/api/asignaciones/${asignacionId}`, {
    method: 'DELETE'
  });
}

export async function getAsistencias() {
  return request<Asistencia[]>('/api/asistencias');
}

export async function getDispositivos() {
  return request<Array<{ id: string; nombre: string; ip_local: string | null; estado: string; ultimo_heartbeat: string | null; tiene_password?: boolean; password_pendiente?: boolean; codigo_enrol?: string | null }>>('/api/dispositivos');
}

export async function getLogs() {
  return request<Array<{ id: string; dispositivo_id: string | null; registros_enviados: number; registros_ok: number; estado: string; detalle: string | null; fecha: string | null }>>('/api/logs');
}

export async function clearLogs() {
  return request<{ ok: boolean } | { error: string }>('/api/logs', {
    method: 'DELETE'
  });
}

export async function getErp() {
  return request<ErpIntegration[]>('/api/erp');
}

export async function createErp(payload: { nombre: string; tipo: string; webhookUrl: string; headers: string; fieldMap: string; envioAuto: boolean; activo?: boolean }) {
  return request<{ ok: boolean; id: string } | { error: string }>('/api/erp', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function deleteErp(erpId: string) {
  return request<{ ok: boolean } | { error: string }>(`/api/erp/${erpId}`, {
    method: 'DELETE'
  });
}

export async function testErp(erpId: string) {
  return request<{ ok: boolean; status_code?: number; mensaje: string; respuesta?: string } | { ok: boolean; mensaje: string }>(`/api/erp/${erpId}/test`, {
    method: 'POST'
  });
}

