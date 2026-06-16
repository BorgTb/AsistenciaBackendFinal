"""
Emula identificarPorRostro() del ESP32.
Referencia: esp32.ino:672-714
"""
import io
import json
import base64
from PIL import Image


def _raw_jpeg_bytes():
    img = Image.new('RGB', (16, 16), (50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=60)
    return buf.getvalue()


def _b64_jpeg():
    return base64.b64encode(_raw_jpeg_bytes()).decode()


class TestEmuladorIdentificacionFacial:
    """Simula identificacion facial del ESP32 via HTTP."""

    def test_identificar_octet_stream_sin_rostros(self, client):
        resp = client.post('/api/facial/identificar',
            data=_raw_jpeg_bytes(),
            content_type='application/octet-stream')
        assert resp.status_code == 404

    def test_identificar_octet_stream_con_rostro(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '30.000.000-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_jpeg()
        })
        resp = client.post('/api/facial/identificar',
            data=_raw_jpeg_bytes(),
            content_type='application/octet-stream')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'persona_id' in data

    def test_identificar_json_base64(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'B64', 'rut': '30.000.000-2'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_jpeg()
        })
        resp = client.post('/api/facial/identificar',
            json={'imagen': _b64_jpeg()},
            content_type='application/json')
        assert resp.status_code == 200

    def test_codigo_http_404_de_esp32_es_esperado(self, client, admin_token):
        """El ESP32 trata 404 como 'rostro no reconocido' — debe ser silencioso."""
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P404', 'rut': '30.000.000-3'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_jpeg()
        })
        dummy_jpg = Image.new('RGB', (1, 1), (255, 0, 0))
        buf = io.BytesIO()
        dummy_jpg.save(buf, format='JPEG')
        raw = buf.getvalue()
        resp = client.post('/api/facial/identificar',
            data=raw, content_type='application/octet-stream')
        assert resp.status_code == 404
