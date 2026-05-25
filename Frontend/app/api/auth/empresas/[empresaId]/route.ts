import { proxyJsonRequest } from '../../../_proxy';

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ empresaId: string }> }
) {
  const { empresaId } = await params;
  const headers: Record<string, string> = {};
  const auth = request.headers.get('authorization');
  if (auth) headers['Authorization'] = auth;
  return proxyJsonRequest(`/api/auth/empresas/${empresaId}`, { method: 'DELETE', headers }, request);
}
