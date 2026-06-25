from unittest.mock import patch


def _enrolar_dispositivo(client, token, nombre='Test', mac='AA:BB:CC:DD:EE:70', ip='192.168.1.70'):
    pin_resp = client.post('/api/auth/dispositivos/generar-pin',
        headers={'Authorization': f'Bearer {token}'},
        json={'nombre': nombre})
    pin = pin_resp.get_json()['pin']
    enrol_resp = client.post('/api/auth/dispositivos/enrolar', json={
        'codigo': pin, 'mac': mac, 'ip': ip
    })
    return enrol_resp.get_json()['dispositivo_id']


class TestSyncDispositivos:
    """Tests para POST /api/dispositivos/sync y /sync/<tipo>"""

    def test_sync_requires_auth(self, client):
        resp = client.post('/api/dispositivos/sync')
        assert resp.status_code == 401

    def test_sync_sin_dispositivos(self, client, admin_token):
        resp = client.post('/api/dispositivos/sync',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is False
        assert 'No hay dispositivos enrolados' in data['mensaje']

    def test_sync_tipo_invalido(self, client, admin_token):
        resp = client.post('/api/dispositivos/sync/invalido',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 400
        assert 'no valido' in resp.get_json()['error']

    def test_sync_tipo_personas(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:71', ip='192.168.1.71')
        with patch('eventos_mqtt.notificar_sincronizacion'):
            resp = client.post('/api/dispositivos/sync/personas',
                headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_sync_tipo_turnos(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:72', ip='192.168.1.72')
        with patch('eventos_mqtt.notificar_sincronizacion'):
            resp = client.post('/api/dispositivos/sync/turnos',
                headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_sync_tipo_asistencias(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:73', ip='192.168.1.73')
        with patch('eventos_mqtt.notificar_sincronizacion'):
            resp = client.post('/api/dispositivos/sync/asistencias',
                headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_sync_tipo_asignaciones(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:74', ip='192.168.1.74')
        with patch('eventos_mqtt.notificar_sincronizacion'):
            resp = client.post('/api/dispositivos/sync/asignaciones',
                headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_sync_todas_con_dispositivos(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:75', ip='192.168.1.75')
        with patch('mqtt_handler.enviar_comando_dispositivo', return_value=True):
            resp = client.post('/api/dispositivos/sync',
                headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        assert 'enviada' in resp.get_json()['mensaje']

    def test_sync_empleador(self, client, empleador_token):
        _enrolar_dispositivo(client, empleador_token,
            mac='AA:BB:CC:DD:EE:76', ip='192.168.1.76')
        with patch('mqtt_handler.enviar_comando_dispositivo', return_value=True):
            resp = client.post('/api/dispositivos/sync',
                headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_sync_db_error(self, client, admin_token):
        mock_conn = __import__('unittest').mock.MagicMock()
        mock_cur = __import__('unittest').mock.MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.dispositivos.get_connection', return_value=mock_conn):
            resp = client.post('/api/dispositivos/sync',
                headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 500
