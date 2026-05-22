import { proxyJsonRequest } from '../_proxy';

export async function GET() {
  return proxyJsonRequest('/api/personas', { method: 'GET' });
}

export async function POST(request: Request) {
  return proxyJsonRequest('/api/personas', {
    method: 'POST',
    body: await request.text()
  });
}
