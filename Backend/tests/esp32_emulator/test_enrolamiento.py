"""
Emula el enrolamiento de dispositivo del ESP32:
1. Admin genera PIN → se almacena en dispositivos con enrolado=FALSE
2. ESP32 hace POST /api/dispositivos/enrolar con PIN + MAC + IP
3. Backend valida y vincula el dispositivo

Referencia: esp32.ino:590-632 (enrolarDispositivo en backend)
"""


class TestEmuladorEnrolamiento:
    """Simula el flujo de enrolamiento del ESP32."""

    def test_pin_es_generado_y_consumido(self, client, admin_token):
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Reloj 1'})
        assert pin_resp.status_code == 200
        data = pin_resp.get_json()
        assert data['ok'] is True
        assert len(data['pin']) == 8

        enrol_resp = client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': data['pin'], 'mac': '11:22:33:44:55:66', 'ip': '192.168.1.50'})
        assert enrol_resp.status_code == 200
        assert enrol_resp.get_json()['ok'] is True

        duplicado = client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': data['pin'], 'mac': '66:55:44:33:22:11', 'ip': '192.168.1.51'})
        assert duplicado.status_code == 404

    def test_enrolamiento_sin_token(self, client):
        resp = client.post('/api/auth/dispositivos/enrolar',
            json={'codigo': 'XXXXXXXX', 'mac': 'AA:BB:CC:DD:EE:FF', 'ip': '10.0.0.1'})
        assert resp.status_code == 404

    def test_pin_invalido(self, client, admin_token):
        resp = client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': 'NOTAPIN!', 'mac': 'AA:BB:CC:DD:EE:FF', 'ip': '10.0.0.1'})
        assert resp.status_code == 404

    def test_dispositivo_enrolado_aparece_en_lista(self, client, admin_token):
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP32-Enroll'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': 'FE:DC:BA:98:76:54', 'ip': '10.10.10.10'})

        resp = client.get('/api/dispositivos',
            headers={'Authorization': f'Bearer {admin_token}'})
        dispositivos = resp.get_json()
        enrolado = [d for d in dispositivos if d.get('mac_address') == 'FE:DC:BA:98:76:54']
        assert len(enrolado) == 1
        assert enrolado[0]['enrolado'] is True
