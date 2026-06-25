def _enrolar_dispositivo(client, token, nombre='Test', mac='AA:BB:CC:DD:EE:50', ip='192.168.1.50'):
    pin_resp = client.post('/api/auth/dispositivos/generar-pin',
        headers={'Authorization': f'Bearer {token}'},
        json={'nombre': nombre})
    pin = pin_resp.get_json()['pin']
    enrol_resp = client.post('/api/auth/dispositivos/enrolar', json={
        'codigo': pin, 'mac': mac, 'ip': ip
    })
    return enrol_resp.get_json()['dispositivo_id']


class TestDeviceSyncAsistencias:
    """Tests para GET /api/asistencias/device-sync"""

    def test_device_sync_sin_mac(self, client):
        resp = client.get('/api/asistencias/device-sync')
        assert resp.status_code == 400

    def test_device_sync_sin_datos(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:51', ip='192.168.1.51')
        resp = client.get('/api/asistencias/device-sync',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:51'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['registros'] == []
        assert data['max_id'] == 0

    def test_device_sync_con_asistencias(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:52', ip='192.168.1.52')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.111.111-1'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada',
            'metodo': 'facial', 'origen': 'dispositivo'
        }, headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:52'})
        resp = client.get('/api/asistencias/device-sync',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:52'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['registros']) >= 1
        assert data['max_id'] > 0
        r = data['registros'][0]
        assert 'id' in r
        assert 'persona_id' in r
        assert 'rut' in r
        assert 'tipo' in r

    def test_device_sync_with_since_id(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:53', ip='192.168.1.53')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.111.111-2'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        })
        resp = client.get('/api/asistencias/device-sync?since_id=99999',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:53'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['registros'] == []
        assert data['max_id'] == 0


class TestDeleteAsistenciasDevice:
    """Tests para DELETE /api/asistencias/device"""

    def test_delete_device_sin_mac(self, client):
        resp = client.delete('/api/asistencias/device')
        assert resp.status_code == 400

    def test_delete_device_mac_inexistente(self, client):
        resp = client.delete('/api/asistencias/device',
            headers={'X-Device-MAC': 'ZZ:ZZ:ZZ:ZZ:ZZ:ZZ'})
        # MAC no encontrada → dispositivo_id None → 400
        assert resp.status_code == 400

    def test_delete_device_sin_asistencias(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:54', ip='192.168.1.54')
        resp = client.delete('/api/asistencias/device',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:54'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['eliminadas'] == 0

    def test_delete_device_con_asistencias(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:55', ip='192.168.1.55')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.111.111-3'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        }, headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:55'})
        resp = client.delete('/api/asistencias/device',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:55'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['eliminadas'] >= 1


class TestUpdateAsistencia:
    """Tests para PUT /api/asistencias/<id>"""

    def test_update_not_found(self, client, admin_token):
        resp = client.put('/api/asistencias/99999',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Editado'})
        assert resp.status_code == 404

    def test_update_admin_success(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.111.111-4'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        })
        resp = client.put('/api/asistencias/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Editado', 'tipo': 'salida'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_update_sin_cambios(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.111.111-5'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        })
        resp = client.put('/api/asistencias/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 200
        assert resp.get_json()['mensaje'] == 'Sin cambios'

    def test_update_no_auth(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.111.111-5'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        })
        resp = client.put('/api/asistencias/1', json={'nombre': 'X'})
        # token_opcional setea rol=None, sin dispositivo → 403
        assert resp.status_code == 403

    def test_update_empleador_otra_empresa(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.111.111-6', 'email': 'p6@x.cl'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        })
        resp = client.put('/api/asistencias/1',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'X'})
        assert resp.status_code == 403


class TestDeleteAsistencia:
    """Tests para DELETE /api/asistencias/<id>"""

    def test_delete_not_found(self, client, admin_token):
        resp = client.delete('/api/asistencias/99999',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_delete_admin_success(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.111.111-7'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        })
        resp = client.delete('/api/asistencias/1',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_delete_empleador_success(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'PEmp', 'rut': '20.111.111-1', 'email': 'pe@e.cl'})
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'PEmp', 'tipo': 'salida'
        })
        resp = client.delete('/api/asistencias/1',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_delete_no_auth(self, client):
        resp = client.delete('/api/asistencias/1')
        assert resp.status_code == 403

    def test_delete_empleador_otra_empresa(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'PAdmin', 'rut': '30.111.111-1'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'PAdmin', 'tipo': 'entrada'
        })
        resp = client.delete('/api/asistencias/1',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 404

    def test_delete_device_success(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token,
            mac='AA:BB:CC:DD:EE:56', ip='192.168.1.56')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'PD', 'rut': '40.111.111-1'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'PD', 'tipo': 'entrada'
        }, headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:56'})
        resp = client.delete('/api/asistencias/1',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:56'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
