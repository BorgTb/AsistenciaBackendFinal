import { proxyJsonRequest } from '../../../_proxy';

export async function GET(request: Request, { params }: { params: Promise<{ erpId: string }> }) {
  const { erpId } = await params;
  return proxyJsonRequest(`/api/erp/${erpId}/estado`, { method: 'GET' }, request);
}
