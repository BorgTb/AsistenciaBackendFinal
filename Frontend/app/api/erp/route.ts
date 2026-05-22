import { proxyJsonRequest } from '../_proxy';

export async function GET() {
  return proxyJsonRequest('/api/erp', { method: 'GET' });
}

export async function POST(request: Request) {
  return proxyJsonRequest('/api/erp', {
    method: 'POST',
    body: await request.text()
  });
}