import { proxyJsonRequest } from '../../../_proxy';

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ userId: string }> }
) {
  const { userId } = await params;
  const headers: Record<string, string> = {};
  const auth = request.headers.get('authorization');
  if (auth) headers['Authorization'] = auth;

  return proxyJsonRequest(`/api/auth/usuarios/${userId}`, {
    method: 'DELETE',
    headers
  });
}
