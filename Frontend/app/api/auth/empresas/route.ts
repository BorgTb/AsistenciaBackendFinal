import { proxyJsonRequest } from '../../_proxy';

export async function GET(request: Request) {
  const headers: Record<string, string> = {};
  const auth = request.headers.get('authorization');
  if (auth) headers['Authorization'] = auth;
  return proxyJsonRequest('/api/auth/empresas', { method: 'GET', headers }, request);
}

export async function POST(request: Request) {
  const headers: Record<string, string> = {};
  const auth = request.headers.get('authorization');
  if (auth) headers['Authorization'] = auth;
  return proxyJsonRequest('/api/auth/empresas', { method: 'POST', body: await request.text(), headers }, request);
}
