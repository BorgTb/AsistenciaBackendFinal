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

export async function changePassword(passwordActual: string, passwordNueva: string) {
  return request<{ ok: boolean; mensaje: string }>('/api/auth/change-password', {
    method: 'PUT',
    body: JSON.stringify({ password_actual: passwordActual, password_nueva: passwordNueva })
  });
}

export async function generarPinEnrolamiento() {
  return request<{ ok: boolean; pin: string; dispositivo_id: number }>('/api/auth/dispositivos/generar-pin', {
    method: 'POST'
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

export async function createEmpresa(payload: { nombre: string; rut_empresa?: string; email_contacto?: string; telefono?: string; direccion?: string }) {
  return request<{ ok: boolean; id: number; mensaje: string }>('/api/auth/empresas', {
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
