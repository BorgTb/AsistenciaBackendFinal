import { proxyJsonRequest } from '../../../_proxy';

export async function PUT(request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  const { personaId } = await params;
  return proxyJsonRequest(`/api/personas/${personaId}/huella`, {
    method: 'PUT',
    body: await request.text()
  }, request);
}
