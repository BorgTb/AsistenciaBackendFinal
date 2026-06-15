import { proxyJsonRequest } from '../../../_proxy';

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ userId: string }> }
) {
  const { userId } = await params;
  return proxyJsonRequest(`/api/auth/usuarios/${userId}`, {
    method: 'DELETE'
  }, request);
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ userId: string }> }
) {
  const { userId } = await params;
  return proxyJsonRequest(`/api/auth/usuarios/${userId}`, {
    method: 'PUT',
    body: request.body
  }, request);
}
