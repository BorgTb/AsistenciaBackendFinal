import { proxyJsonRequest } from '../../_proxy';

export async function POST(request: Request) {
  return proxyJsonRequest('/api/dispositivos/verificar', {
    method: 'POST',
    body: await request.text()
  }, request);
}
