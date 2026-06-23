import { proxyJsonRequest } from '../../_proxy';

export async function PUT(request: Request, { params }: { params: Promise<{ turnoId: string }> }) {
  const { turnoId } = await params;
  return proxyJsonRequest(`/api/turnos/${turnoId}`, { method: 'PUT', body: await request.text() }, request);
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ turnoId: string }> }) {
  const { turnoId } = await params;
  return proxyJsonRequest(`/api/turnos/${turnoId}`, { method: 'DELETE' }, _request);
}
