import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest';
import { server } from './handlers';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('lib/api.ts', () => {
  it('getPersonas returns array', async () => {
    const { getPersonas } = await import('@/lib/api');
    const result = await getPersonas();
    expect(result).not.toBeNull();
    expect(Array.isArray(result)).toBe(true);
    expect(result![0].nombre).toBe('Juan');
  });

  it('getTurnos returns array', async () => {
    const { getTurnos } = await import('@/lib/api');
    const result = await getTurnos();
    expect(result).not.toBeNull();
    expect(result![0].nombre).toBe('Turno A');
  });

  it('getAsistencias returns array', async () => {
    const { getAsistencias } = await import('@/lib/api');
    const result = await getAsistencias();
    expect(result).not.toBeNull();
    expect(result![0].tipo).toBe('entrada');
  });

  it('createPersona returns ok', async () => {
    const { createPersona } = await import('@/lib/api');
    const result = await createPersona({ nombre: 'Nuevo', rut: '99.999.999-9' });
    expect(result).not.toBeNull();
    expect(result!.ok).toBe(true);
  });

  it('getDispositivos returns array', async () => {
    const { getDispositivos } = await import('@/lib/api');
    const result = await getDispositivos();
    expect(Array.isArray(result)).toBe(true);
  });

  it('getErp returns array', async () => {
    const { getErp } = await import('@/lib/api');
    const result = await getErp();
    expect(Array.isArray(result)).toBe(true);
  });
});

describe('lib/auth-api.ts', () => {
  it('loginRequest returns token and user', async () => {
    const { loginRequest } = await import('@/lib/auth-api');
    const result = await loginRequest('admin@empresa.cl', 'admin123');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.token).toBe('fake-jwt-token-abc123');
      expect(result.user.email).toBe('admin@empresa.cl');
    }
  });

  it('fetchMe returns user', async () => {
    const { fetchMe } = await import('@/lib/auth-api');
    const result = await fetchMe();
    expect(result.user.rol).toBe('admin');
  });

  it('saveToken and hasToken work', async () => {
    const { saveToken, hasToken, clearToken } = await import('@/lib/auth-api');
    saveToken('test-token');
    expect(hasToken()).toBe(true);
    clearToken();
    expect(hasToken()).toBe(false);
  });

  it('getUsuarios returns array', async () => {
    const { getUsuarios } = await import('@/lib/auth-api');
    const result = await getUsuarios();
    expect(result).not.toBeNull();
    expect(Array.isArray(result)).toBe(true);
  });

  it('getEmpresas returns array', async () => {
    const { getEmpresas } = await import('@/lib/auth-api');
    const result = await getEmpresas();
    expect(result).not.toBeNull();
    expect(Array.isArray(result)).toBe(true);
  });
});
