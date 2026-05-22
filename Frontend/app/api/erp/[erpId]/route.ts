import { proxyJsonRequest } from '../../_proxy';

export async function DELETE(_request: Request, { params }: { params: Promise<{ erpId: string }> }) {
  const { erpId } = await params;
  return proxyJsonRequest(`/api/erp/${erpId}`, { method: 'DELETE' });
}