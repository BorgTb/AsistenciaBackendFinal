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

export async function proxyJsonRequest(path: string, init?: RequestInit) {
  const response = await fetch(`${backendUrl}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {})
    },
    cache: 'no-store'
  });

  const contentType = response.headers.get('content-type') || '';
  const headers = copyHeaders(response.headers);
  headers.delete('content-encoding');
  headers.delete('transfer-encoding');

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
