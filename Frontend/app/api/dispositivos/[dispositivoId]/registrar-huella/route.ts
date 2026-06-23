import { proxyJsonRequest } from '../../../_proxy';

export async function POST(request: Request, { params }: { params: Promise<{ dispositivoId: string }> }) {
  const { dispositivoId } = await params;
  return proxyJsonRequest(`/api/dispositivos/${dispositivoId}/registrar-huella`, {
    method: 'POST',
    body: await request.text()
  }, request);
}
