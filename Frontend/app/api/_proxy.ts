import { NextResponse } from 'next/server';

const backendUrl = process.env.FLASK_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:5000';

function copyHeaders(source: Headers) {
  const headers = new Headers();
  source.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower === 'host' || lower === 'connection' || lower === 'content-length') return;
    headers.set(key, value);
  });
  return headers;
}

export async function proxyJsonRequest(path: string, init?: RequestInit, incoming?: Request) {
  const forwardedHeaders: Record<string, string> = {
    'User-Agent': 'SasFrontend/1.0'
  };

  if (incoming) {
    const auth = incoming.headers.get('Authorization');
    if (auth) {
      forwardedHeaders['Authorization'] = auth;
    } else {
      const cookie = incoming.headers.get('Cookie') || '';
      const match = cookie.match(/(?:^|;\s*)sas_token=([^;]+)/);
      if (match) {
        forwardedHeaders['Authorization'] = `Bearer ${decodeURIComponent(match[1])}`;
      }
    }
    const mac = incoming.headers.get('X-Device-MAC');
    if (mac) forwardedHeaders['X-Device-MAC'] = mac;
  }

  const response = await fetch(`${backendUrl}${path}`, {
    ...init,
    headers: {
      ...forwardedHeaders,
      'Content-Type': 'application/json',
      ...(init?.headers || {})
    },
    cache: 'no-store'
  });

  const contentType = response.headers.get('content-type') || '';
  const headers = copyHeaders(response.headers);
  headers.delete('content-encoding');
  headers.delete('transfer-encoding');

  if (response.status === 403) {
    const bodyPreview = await response.text().then(t => t.slice(0, 200));
    if (bodyPreview.includes('cloudflare') || bodyPreview.includes('captcha') || bodyPreview.includes('challenge')) {
      return NextResponse.json({
        error: 'Bloqueado por Cloudflare. Verifica que FLASK_API_BASE_URL apunte directamente al backend local (127.0.0.1:5000) y no al dominio público.'
      }, { status: 502 });
    }
  }

  if (contentType.includes('application/json')) {
    const data = await response.json();
    return NextResponse.json(data, { status: response.status, headers });
  }

  const body = await response.text();
  return new Response(body, {
    status: response.status,
    headers
  });
}
