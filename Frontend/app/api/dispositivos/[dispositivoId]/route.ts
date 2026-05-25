import { proxyJsonRequest } from '../../_proxy';

export async function PUT(request: Request, { params }: { params: Promise<{ dispositivoId: string }> }) {
  const { dispositivoId } = await params;
  return proxyJsonRequest(`/api/dispositivos/${dispositivoId}`, {
    method: 'PUT',
    body: await request.text()
  }, request);
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ dispositivoId: string }> }) {
  const { dispositivoId } = await params;
  return proxyJsonRequest(`/api/dispositivos/${dispositivoId}`, { method: 'DELETE' }, _request);
}
