import { proxyJsonRequest } from '../../../_proxy';

export async function POST(request: Request, { params }: { params: Promise<{ erpId: string }> }) {
  const { erpId } = await params;
  return proxyJsonRequest(`/api/erp/${erpId}/test`, {
    method: 'POST',
    body: await request.text()
  }, request);
}