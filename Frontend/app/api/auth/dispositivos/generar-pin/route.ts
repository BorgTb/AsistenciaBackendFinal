import { proxyJsonRequest } from '../../../_proxy';

export async function POST(request: Request) {
  const headers: Record<string, string> = {};
  const auth = request.headers.get('authorization');
  if (auth) headers['Authorization'] = auth;

  const body = await request.text();

  return proxyJsonRequest('/api/auth/dispositivos/generar-pin', {
    method: 'POST',
    headers,
    body: body || undefined
  }, request);
}
