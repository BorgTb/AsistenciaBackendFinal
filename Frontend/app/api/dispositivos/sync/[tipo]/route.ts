import { proxyJsonRequest } from '../../../_proxy';

export async function POST(request: Request, { params }: { params: { tipo: string } }) {
  return proxyJsonRequest(`/api/dispositivos/sync/${params.tipo}`, {
    method: 'POST',
    body: await request.text()
  }, request);
}
