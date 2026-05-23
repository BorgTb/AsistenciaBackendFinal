import { proxyJsonRequest } from '../../_proxy';

export async function PUT(request: Request) {
  const headers: Record<string, string> = {};
  const auth = request.headers.get('authorization');
  if (auth) headers['Authorization'] = auth;

  return proxyJsonRequest('/api/auth/change-password', {
    method: 'PUT',
    body: await request.text(),
    headers
  });
}
