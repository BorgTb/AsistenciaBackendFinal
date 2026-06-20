import { proxyJsonRequest } from '../../_proxy';

export async function POST(request: Request) {
  return proxyJsonRequest('/api/auth/register-company', {
    method: 'POST',
    body: await request.text()
  }, request);
}
