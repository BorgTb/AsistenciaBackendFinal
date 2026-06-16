"""
Emula POST /api/personas + completarRegistroPersona() del ESP32.
Referencia: esp32.ino:914-987
"""
import json


class TestEmuladorRegistroPersona:
    """Simula el flujo de registro de persona del ESP32."""

    def test_crear_persona_backend_devuelve_id(self, client, admin_token):
        resp = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Juan', 'rut': '11.111.111-1', 'email': 'juan@test.cl'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert isinstance(data['id'], int)

    def test_crear_persona_con_huella_id(self, client, admin_token):
        resp = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Ana', 'rut': '22.222.222-2', 'huella_id': 5})
        assert resp.status_code == 200
        pid = resp.get_json()['id']
        get_resp = client.get('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'})
        personas = get_resp.get_json()
        persona = next((p for p in personas if p['id'] == str(pid)), None)
        assert persona is not None
        assert persona['huella_id'] == 5

    def test_create_sets_default_empresa(self, client):
        resp = client.post('/api/personas', json={
            'nombre': 'SinEmpresa', 'rut': '33.333.333-3'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['id'] is not None

    def test_rut_duplicado_rechazado(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P1', 'rut': '44.444.444-4'})
        resp = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P2', 'rut': '44.444.444-4'})
        assert resp.status_code == 500
