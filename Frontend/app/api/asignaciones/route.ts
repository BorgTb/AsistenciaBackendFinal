import { proxyJsonRequest } from '../_proxy';

export async function GET(request: Request) {
  return proxyJsonRequest('/api/asignaciones', { method: 'GET' }, request);
}

export async function POST(request: Request) {
  return proxyJsonRequest('/api/asignaciones', {
    method: 'POST',
    body: await request.text()
  }, request);
}
