import { proxyJsonRequest } from '../_proxy';

export async function GET(request: Request) {
  return proxyJsonRequest('/api/logs', { method: 'GET' }, request);
}

export async function DELETE(request: Request) {
  return proxyJsonRequest('/api/logs', { method: 'DELETE' }, request);
}