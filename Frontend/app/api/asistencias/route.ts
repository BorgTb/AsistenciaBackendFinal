import { proxyJsonRequest } from '../_proxy';

export async function GET() {
  return proxyJsonRequest('/api/asistencias', { method: 'GET' });
}

export async function POST(request: Request) {
  return proxyJsonRequest('/api/asistencias', {
    method: 'POST',
    body: await request.text()
  });
}
