import { proxyJsonRequest } from '../_proxy';

export async function GET() {
  return proxyJsonRequest('/api/asignaciones', { method: 'GET' });
}

export async function POST(request: Request) {
  return proxyJsonRequest('/api/asignaciones', {
    method: 'POST',
    body: await request.text()
  });
}
