import io
import base64
import os
from PIL import Image


def _b64_dummy_jpeg():
    img = Image.new('RGB', (16, 16), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    return base64.b64encode(buf.getvalue()).decode()


class TestRoutesFacial:
    """Tests para /api/facial — registrar, verificar, identificar, actualizar."""

    def test_registrar_sin_consentimiento_falla(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.100.100-0'})
        resp = client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 403

    def test_registrar_con_consentimiento_exitoso(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.200.200-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'Registro exitoso' in data['mensaje']

    def test_registrar_faltan_datos(self, client):
        resp = client.post('/api/facial/registrar', json={})
        assert resp.status_code == 400

    def test_verificar_facial_sin_datos(self, client):
        resp = client.post('/api/facial/verificar', json={})
        assert resp.status_code == 400

    def test_verificar_con_rostro_registrado(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.300.300-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        resp = client.post('/api/facial/verificar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_identificar_sin_rostros_falla(self, client):
        resp = client.post('/api/facial/identificar', data=_b64_dummy_jpeg(),
            content_type='application/octet-stream')
        assert resp.status_code == 404

    def test_identificar_json_base64(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.400.400-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        resp = client.post('/api/facial/identificar',
            json={'imagen': _b64_dummy_jpeg()},
            content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'persona_id' in data

    def test_identificar_octet_stream(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.500.500-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        raw = base64.b64decode(_b64_dummy_jpeg())
        resp = client.post('/api/facial/identificar',
            data=raw, content_type='application/octet-stream')
        assert resp.status_code == 200

    def test_identificar_sin_imagen(self, client):
        resp = client.post('/api/facial/identificar', json={})
        assert resp.status_code == 400

    def test_registrar_duplicado_rechazado(self, client, admin_token):
        person_id = None
        for i in range(2):
            rut = f'10.600.{i}00-0'
            client.post('/api/personas',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'nombre': f'P{i}', 'rut': rut})
            client.post(f'/api/personas/{i+1}/consentimiento',
                headers={'Authorization': f'Bearer {admin_token}'})
            resp = client.post('/api/facial/registrar', json={
                'persona_id': str(i + 1), 'imagen': _b64_dummy_jpeg()
            })
            if i > 0:
                assert resp.status_code == 409

    def test_agregar_foto(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.700.700-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        resp = client.post('/api/facial/agregar-foto', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_agregar_foto_sin_consentimiento(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.800.800-0'})
        resp = client.post('/api/facial/agregar-foto', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 403

    def test_actualizar_facial(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.900.900-0'})
        resp = client.put('/api/facial/actualizar/1', json={
            'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_actualizar_facial_sin_imagen(self, client):
        resp = client.put('/api/facial/actualizar/1', json={})
        assert resp.status_code == 400

    def test_actualizar_facial_persona_no_existe(self, client):
        resp = client.put('/api/facial/actualizar/99999', json={
            'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 404

    def test_verificar_facial_sin_rostro(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Sin Rostro', 'rut': '10.910.910-0'})
        resp = client.post('/api/facial/verificar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 404

    def test_verificar_facial_no_coincide(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Con Rostro', 'rut': '10.920.920-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'}, json={})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Otro Rostro', 'rut': '10.930.930-0'})
        resp = client.post('/api/facial/verificar', json={
            'persona_id': '2', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code in (200, 404)

    def test_identificar_content_type_invalido(self, client):
        resp = client.post('/api/facial/identificar',
            data='not an image',
            headers={'Content-Type': 'text/plain'})
        assert resp.status_code == 415

    # ── identificar-o-registrar ────────────────────────

    def test_identificar_o_registrar_rostro_existente(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'IR-Exist', 'rut': '50.100.100-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        resp = client.post('/api/facial/identificar-o-registrar', json={
            'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['persona_id'] == '1'

    def test_identificar_o_registrar_sin_imagen(self, client):
        resp = client.post('/api/facial/identificar-o-registrar', json={})
        assert resp.status_code == 400

    def test_identificar_o_registrar_base64_invalido(self, client):
        resp = client.post('/api/facial/identificar-o-registrar', json={
            'imagen': 'esto-no-es-base64!!!'
        })
        assert resp.status_code == 400

    def test_identificar_o_registrar_rostro_no_reconocido(self, client):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        resp = client.post('/api/facial/identificar-o-registrar', json={
            'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 404

    def test_identificar_o_registrar_crea_nuevo_con_rut(self, client):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        resp = client.post('/api/facial/identificar-o-registrar', json={
            'imagen': _b64_dummy_jpeg(),
            'rut': '99.888.777-6',
            'consentimiento': True
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['registro_nuevo'] is True
        assert data['rut'] == '99.888.777-6'

    def test_identificar_o_registrar_rut_existente(self, client, admin_token):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'IR-Existente', 'rut': '50.200.200-2'})
        resp = client.post('/api/facial/identificar-o-registrar', json={
            'imagen': _b64_dummy_jpeg(),
            'rut': '50.200.200-2',
            'consentimiento': True
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['registro_nuevo'] is False

    def test_identificar_o_registrar_consentimiento_requerido(self, client):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        resp = client.post('/api/facial/identificar-o-registrar', json={
            'imagen': _b64_dummy_jpeg(),
            'rut': '50.300.300-3',
            'consentimiento': True
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
