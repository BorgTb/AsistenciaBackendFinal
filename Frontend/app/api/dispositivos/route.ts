import { proxyJsonRequest } from '../_proxy';

export async function GET() {
  return proxyJsonRequest('/api/dispositivos', { method: 'GET' });
}