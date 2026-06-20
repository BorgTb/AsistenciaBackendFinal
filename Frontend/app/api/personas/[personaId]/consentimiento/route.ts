import { proxyJsonRequest } from '../../../_proxy';

export async function POST(request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  const { personaId } = await params;
  return proxyJsonRequest(`/api/personas/${personaId}/consentimiento`, {
    method: 'POST',
    body: await request.text()
  }, request);
}
