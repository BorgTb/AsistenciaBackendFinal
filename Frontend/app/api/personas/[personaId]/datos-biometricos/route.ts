import { proxyJsonRequest } from '../../../_proxy';

export async function DELETE(request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  const { personaId } = await params;
  return proxyJsonRequest(`/api/personas/${personaId}/datos-biometricos`, {
    method: 'DELETE'
  }, request);
}
