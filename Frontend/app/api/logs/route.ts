import { proxyJsonRequest } from '../_proxy';

export async function GET() {
  return proxyJsonRequest('/api/logs', { method: 'GET' });
}

export async function DELETE() {
  return proxyJsonRequest('/api/logs', { method: 'DELETE' });
}