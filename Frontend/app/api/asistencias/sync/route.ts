import { proxyJsonRequest } from '../../_proxy';

export async function POST(request: Request) {
  return proxyJsonRequest('/api/asistencias/sync', {
    method: 'POST',
    body: await request.text()
  });
}
