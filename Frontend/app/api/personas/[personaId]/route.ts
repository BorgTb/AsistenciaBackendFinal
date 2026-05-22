import { proxyJsonRequest } from '../../_proxy';

export async function PUT(request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  const { personaId } = await params;
  return proxyJsonRequest(`/api/personas/${personaId}`, {
    method: 'PUT',
    body: await request.text()
  });
}

export async function PATCH(request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  const { personaId } = await params;
  return proxyJsonRequest(`/api/personas/${personaId}`, {
    method: 'PATCH',
    body: await request.text()
  });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  const { personaId } = await params;
  return proxyJsonRequest(`/api/personas/${personaId}`, { method: 'DELETE' });
}
