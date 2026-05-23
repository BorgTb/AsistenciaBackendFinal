import { proxyJsonRequest } from '../../_proxy';

export async function POST(request: Request) {
  return proxyJsonRequest('/api/auth/login', {
    method: 'POST',
    body: await request.text()
  });
}
