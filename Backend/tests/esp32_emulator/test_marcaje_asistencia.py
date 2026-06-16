"""
Emula postAsistenciaEnBackend() y procesarAsistencia() del ESP32.
Referencia: esp32.ino:736-812
"""
import json


class TestEmuladorMarcajeAsistencia:
    """Simula marcaje de asistencia desde el ESP32."""

    def test_marcar_entrada(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.000.000-0'})
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada',
            'metodo': 'huella', 'origen': 'dispositivo'
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_marcar_salida_alterna(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.000.001-0'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada', 'metodo': 'huella'
        })
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'salida', 'metodo': 'huella'
        })
        assert resp.status_code == 200

    def test_marcar_metodo_facial(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'F', 'rut': '10.000.002-0'})
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'F', 'tipo': 'entrada',
            'metodo': 'facial', 'origen': 'dispositivo'
        })
        assert resp.status_code == 200

    def test_marcar_sin_persona_id_no_falla(self, client):
        resp = client.post('/api/asistencias', json={
            'nombre': 'Anonimo', 'tipo': 'entrada', 'metodo': 'manual'
        })
        assert resp.status_code == 200

    def test_payload_formato_esp32_real(self, client, admin_token):
        """Payload exacto que manda el ESP32 en postAsistenciaEnBackend()."""
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Real', 'rut': '10.000.003-0'})
        payload = {
            'persona_id': '1',
            'nombre': 'Real',
            'tipo': 'entrada',
            'metodo': 'huella',
            'origen': 'dispositivo',
            'sincronizado': True
        }
        resp = client.post('/api/asistencias', json=payload)
        assert resp.status_code == 200
