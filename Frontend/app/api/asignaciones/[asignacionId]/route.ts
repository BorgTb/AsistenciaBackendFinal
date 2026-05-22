import { proxyJsonRequest } from '../../_proxy';

export async function DELETE(_request: Request, { params }: { params: Promise<{ asignacionId: string }> }) {
  const { asignacionId } = await params;
  return proxyJsonRequest(`/api/asignaciones/${asignacionId}`, { method: 'DELETE' });
}
