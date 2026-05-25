import { proxyJsonRequest } from '../_proxy';

export async function GET(request: Request) {
  return proxyJsonRequest('/api/dispositivos', { method: 'GET' }, request);
}