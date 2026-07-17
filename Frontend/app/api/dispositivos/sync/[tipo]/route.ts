import { proxyJsonRequest } from '../../../_proxy';

export async function POST(request: Request, { params }: { params: Promise<{ tipo: string }> }) {
  const { tipo } = await params;
  return proxyJsonRequest(`/api/dispositivos/sync/${tipo}`, {
    method: 'POST',
    body: await request.text()
  }, request);
}
