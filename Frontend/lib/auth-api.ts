import type { AuthUser, EmpresaVinculada } from '@/lib/auth-types';

const baseUrl = '';

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('sas_token');
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {})
    },
    cache: 'no-store'
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }

  return data as T;
}

export interface LoginSuccess {
  ok: true;
  token: string;
  user: AuthUser;
}

export interface LoginNeedEmpresa {
  ok: false;
  need_empresa: true;
  empresas: EmpresaVinculada[];
  user_name: string;
  user_email: string;
}

export type LoginResult = LoginSuccess | LoginNeedEmpresa;

export async function loginRequest(email: string, password: string, empresaId?: number) {
  const body: Record<string, unknown> = { email, password };
  if (empresaId) body.empresa_id = empresaId;
  return request<LoginResult>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(body)
  });
}

export async function registerUser(payload: { nombre: string; email: string; password: string; rol: string; empresa_id?: number }) {
  return request<{ ok: boolean; id: number; mensaje: string }>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export interface UsuarioWeb {
  id: number;
  nombre: string;
  email: string;
  rol: string;
  activo: boolean;
  created_at: string;
  empresa_nombre: string;
  empresa_id: number;
}

export async function fetchMe() {
  return request<{ user: AuthUser }>('/api/auth/me');
}

export async function getUsuarios() {
  return request<UsuarioWeb[]>('/api/auth/usuarios');
}

export async function deleteUsuario(userId: number, empresaId?: number) {
  return request<{ ok: boolean; mensaje: string }>(`/api/auth/usuarios/${userId}`, {
    method: 'DELETE',
    body: empresaId ? JSON.stringify({ empresa_id: empresaId }) : undefined
  });
}

export async function updateUsuario(userId: number, payload: { nombre?: string; email?: string; password?: string; rol?: string; empresa_id?: number; activo?: boolean }) {
  return request<{ ok: boolean; mensaje: string }>(`/api/auth/usuarios/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
}

export async function changePassword(passwordActual: string, passwordNueva: string) {
  return request<{ ok: boolean; mensaje: string }>('/api/auth/change-password', {
    method: 'PUT',
    body: JSON.stringify({ password_actual: passwordActual, password_nueva: passwordNueva })
  });
}

export async function generarPinEnrolamiento(nombre?: string) {
  return request<{ ok: boolean; pin: string; dispositivo_id: number }>('/api/auth/dispositivos/generar-pin', {
    method: 'POST',
    body: nombre ? JSON.stringify({ nombre }) : undefined
  });
}

export async function deleteDispositivo(dispositivoId: string) {
  return request<{ ok: boolean; mensaje: string }>(`/api/dispositivos/${dispositivoId}`, {
    method: 'DELETE'
  });
}

export async function updateDispositivo(dispositivoId: string, nombre: string) {
  return request<{ ok: boolean; id: string; nombre: string }>(`/api/dispositivos/${dispositivoId}`, {
    method: 'PUT',
    body: JSON.stringify({ nombre })
  });
}

export async function verificarDispositivo(ip: string) {
  return request<{ ok: boolean; error?: string; mensaje?: string; datos?: { mac: string; ssid: string; enrolado: boolean; pin?: string } }>('/api/dispositivos/verificar', {
    method: 'POST',
    body: JSON.stringify({ ip })
  });
}

export async function generarPasswordDispositivo(dispositivoId: string) {
  return request<{ ok: boolean; password: string }>(`/api/dispositivos/${dispositivoId}/generar-password`, {
    method: 'POST'
  });
}

export async function eliminarPasswordDispositivo(dispositivoId: string) {
  return request<{ ok: boolean; mensaje: string }>(`/api/dispositivos/${dispositivoId}/password`, {
    method: 'DELETE'
  });
}

export async function registrarHuellaDispositivo(dispositivoId: string, personaId: string) {
  return request<{ ok: boolean; mensaje: string; dispositivo_id: string; persona_id: string }>(`/api/dispositivos/${dispositivoId}/registrar-huella`, {
    method: 'POST',
    body: JSON.stringify({ persona_id: personaId })
  });
}

export async function reiniciarDispositivo(dispositivoId: string) {
  return request<{ ok: boolean; mensaje: string }>(`/api/dispositivos/${dispositivoId}/reiniciar`, {
    method: 'POST'
  });
}

export async function reconectarWifiDispositivo(dispositivoId: string) {
  return request<{ ok: boolean; mensaje: string }>(`/api/dispositivos/${dispositivoId}/wifi-reconnect`, {
    method: 'POST'
  });
}

export async function enviarErp(erpId: string) {
  return request<{ ok: boolean; enviados: number; errores: number; mensaje?: string; ultimo_estado?: unknown }>(`/api/erp/${erpId}/enviar`, {
    method: 'POST'
  });
}

export async function getErpEstado(erpId: string) {
  return request<{ ultimoEnvio: string | null; ultimoEstado: string }>(`/api/erp/${erpId}/estado`);
}

export async function registrarRostro(rut: string, imagenBase64: string) {
  return request<{ ok: boolean; mensaje: string }>(`/api/facial/registrar`, {
    method: 'POST',
    body: JSON.stringify({ rut, imagen: imagenBase64 })
  });
}

export async function agregarFotoRostro(rut: string, imagenBase64: string) {
  return request<{ ok: boolean; id: number; total_fotos: number; mensaje: string }>(`/api/facial/agregar-foto`, {
    method: 'POST',
    body: JSON.stringify({ rut, imagen: imagenBase64 })
  });
}

export interface RegisterCompanyPayload {
  empresa_nombre: string;
  admin_nombre: string;
  admin_email: string;
  admin_password: string;
}

export async function registerCompany(payload: RegisterCompanyPayload) {
  return request<{ ok: boolean; token: string; user: AuthUser; mensaje?: string }>('/api/auth/register-company', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export interface Empresa {
  id: number;
  nombre: string;
  rut_empresa: string;
  email_contacto: string;
  telefono: string;
  direccion: string;
  created_at: string;
}

export async function getEmpresas() {
  return request<Empresa[]>('/api/auth/empresas');
}

export async function createEmpresa(payload: {
  nombre: string;
  rut_empresa?: string;
  email_contacto?: string;
  telefono?: string;
  direccion?: string;
  mode?: string;
  rol_usuario?: string;
  nombre_usuario?: string;
  email_usuario?: string;
  password_usuario?: string;
  usuario_id?: number;
}) {
  return request<{ ok: boolean; id: number; usuario_id?: number; mensaje: string }>('/api/auth/empresas', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function deleteEmpresa(empresaId: number) {
  return request<{ ok: boolean; mensaje: string }>(`/api/auth/empresas/${empresaId}`, {
    method: 'DELETE'
  });
}

export async function asignarUsuarioEmpresa(usuarioId: number, empresaId: number, rol: string) {
  return request<{ ok: boolean; mensaje: string }>('/api/auth/asignar-usuario', {
    method: 'POST',
    body: JSON.stringify({ usuario_id: usuarioId, empresa_id: empresaId, rol })
  });
}

export interface SolicitudEliminacion {
  id: number;
  persona_id: string;
  nombre: string;
  rut: string;
  email_contacto: string;
  estado: 'pendiente' | 'aprobada' | 'rechazada';
  motivo: string;
  codigo_seguimiento: string;
  fecha_solicitud: string | null;
  fecha_resolucion: string | null;
}

export async function solicitarEliminacionDatos(payload: { rut: string; email?: string; motivo?: string }) {
  const response = await fetch('/api/auth/solicitar-eliminacion-datos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    cache: 'no-store'
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data as { ok: boolean; codigo_seguimiento: string; mensaje: string };
}

export async function consultarSolicitudEliminacion(codigo: string) {
  const response = await fetch(`/api/auth/solicitud-eliminacion/${codigo}`, {
    cache: 'no-store'
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data as { ok: boolean; estado: string; fecha_solicitud: string | null; fecha_resolucion: string | null };
}

export async function getSolicitudesEliminacion() {
  return request<SolicitudEliminacion[]>('/api/auth/solicitudes-eliminacion');
}

export async function resolverSolicitudEliminacion(solicitudId: number, estado: 'aprobada' | 'rechazada') {
  return request<{ ok: boolean; mensaje: string }>(`/api/auth/solicitudes-eliminacion/${solicitudId}`, {
    method: 'PUT',
    body: JSON.stringify({ estado })
  });
}

export function saveToken(token: string) {
  if (typeof window !== 'undefined') {
    localStorage.setItem('sas_token', token);
    document.cookie = `sas_token=${token}; path=/; max-age=86400; SameSite=Lax`;
  }
}

export function clearToken() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('sas_token');
    document.cookie = 'sas_token=; path=/; max-age=0';
  }
}

export function hasToken(): boolean {
  return getToken() !== null;
}
