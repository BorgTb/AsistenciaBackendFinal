import { proxyJsonRequest } from '../_proxy';

export async function GET() {
  return proxyJsonRequest('/api/turnos', { method: 'GET' });
}

export async function POST(request: Request) {
  return proxyJsonRequest('/api/turnos', {
    method: 'POST',
    body: await request.text()
  });
}
