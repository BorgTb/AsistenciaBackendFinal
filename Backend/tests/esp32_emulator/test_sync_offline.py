"""
Emula sincronizarAsistencias() y sincronizarPendientes() del ESP32.
Referencia: esp32.ino:998-1034, 1313-1317
"""
import json


class TestEmuladorSyncOffline:
    """Simula sincronizacion offline del ESP32."""

    def test_sync_varios_registros(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P1', 'rut': '20.000.000-1'})
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P2', 'rut': '20.000.000-2'})

        registros = [
            {'persona_id': '1', 'nombre': 'P1', 'tipo': 'entrada', 'metodo': 'huella'},
            {'persona_id': '1', 'nombre': 'P1', 'tipo': 'salida', 'metodo': 'huella'},
            {'persona_id': '2', 'nombre': 'P2', 'tipo': 'entrada', 'metodo': 'facial'},
            {'persona_id': '2', 'nombre': 'P2', 'tipo': 'salida', 'metodo': 'facial'},
            {'persona_id': '1', 'nombre': 'P1', 'tipo': 'entrada', 'metodo': 'huella'},
        ]
        resp = client.post('/api/asistencias/sync', json={'registros': registros})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['insertados'] == 5

    def test_sync_payload_formato_esp32(self, client, admin_token):
        """Payload exacto que manda el ESP32 en sincronizarAsistencias()."""
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Sync', 'rut': '20.000.003-0'})
        payload = {
            'registros': [
                {
                    'persona_id': '1',
                    'nombre': 'Sync',
                    'tipo': 'entrada',
                    'metodo': 'huella'
                }
            ]
        }
        resp = client.post('/api/asistencias/sync', json=payload)
        assert resp.status_code == 200

    def test_sync_crea_turno_y_asignacion(self, client, admin_token):
        """Simula crearTurnoEnBackend + crearAsignacionEnBackend."""
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'TA', 'rut': '20.000.004-0'})
        turno = client.post('/api/turnos', json={
            'nombre': 'Turno Offline', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L,M,X'
        })
        assert turno.status_code == 200
        tid = turno.get_json()['id']
        asig = client.post('/api/asignaciones', json={
            'persona_id': '1', 'turno_id': str(tid)
        })
        assert asig.status_code == 200
