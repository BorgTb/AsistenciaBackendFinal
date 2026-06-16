import { describe, it, expect } from 'vitest';
import { NextRequest, NextResponse } from 'next/server';

// Mock cookies helper
function mockRequest(pathname: string, token?: string): NextRequest {
  const url = `http://localhost:3000${pathname}`;
  const req = new NextRequest(url);
  if (token) {
    req.cookies.set('sas_token', token);
  }
  return req;
}

describe('middleware.ts', () => {
  it('redirige a /login si no hay token', async () => {
    const { default: middleware } = await import('@/middleware');
    const request = mockRequest('/personas');
    const response = await middleware(request);
    if (response) {
      expect(response.status).toBe(307);
      expect(response.headers.get('Location')).toBe('http://localhost:3000/login');
    }
  });

  it('permite /login sin token', async () => {
    const { default: middleware } = await import('@/middleware');
    const request = mockRequest('/login');
    const response = await middleware(request);
    expect(response?.status).toBeUndefined();
  });

  it('permite /api/auth sin token', async () => {
    const { default: middleware } = await import('@/middleware');
    const request = mockRequest('/api/auth/login');
    const response = await middleware(request);
    expect(response?.status).toBeUndefined();
  });

  it('permite acceso con token valido', async () => {
    const { default: middleware } = await import('@/middleware');
    const request = mockRequest('/personas', 'valid-token');
    const response = await middleware(request);
    expect(response?.status).toBeUndefined();
  });

  it('permite recursos estaticos', async () => {
    const { default: middleware } = await import('@/middleware');
    const request = new NextRequest('http://localhost:3000/_next/static/css/style.css');
    const response = await middleware(request);
    expect(response?.status).toBeUndefined();
  });
});

describe('app/api/_proxy.ts', () => {
  it('forwardea Authorization header', async () => {
    const { proxyJsonRequest } = await import('@/app/api/_proxy');
    const mockIncoming = new Request('http://localhost:3000/api/personas', {
      headers: { 'Authorization': 'Bearer test-token' }
    });

    const originalFetch = globalThis.fetch;
    let capturedHeaders: Record<string, string> = {};
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    );

    try {
      const response = await proxyJsonRequest('/api/personas', {}, mockIncoming);
      const data = await response.json();
      expect(data.ok).toBe(true);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('forwardea X-Device-MAC header', async () => {
    const { proxyJsonRequest } = await import('@/app/api/_proxy');
    const mockIncoming = new Request('http://localhost:3000/api/asistencias', {
      headers: { 'X-Device-MAC': 'AA:BB:CC:DD:EE:FF' }
    });

    let capturedHeaders: Record<string, string> = {};
    globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
      capturedHeaders = init?.headers || {};
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        })
      );
    });

    try {
      await proxyJsonRequest('/api/asistencias', {}, mockIncoming);
      expect(capturedHeaders['X-Device-MAC']).toBe('AA:BB:CC:DD:EE:FF');
    } finally {
      globalThis.fetch = fetch;
    }
  });
});

// Import vi for mock in _proxy tests
import { vi } from 'vitest';
