class TestRoutesAsistencias:
    """Tests para /api/asistencias — marcajes, sync, ERP push."""

    def test_listar_asistencias_vacio(self, client):
        resp = client.get('/api/asistencias')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_crear_asistencia_sin_token(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '11.111.111-1'})
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada',
            'metodo': 'facial', 'origen': 'dispositivo'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['id'] is not None

    def test_listar_asistencias_con_datos(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '22.222.222-2'})
        for i in range(3):
            client.post('/api/asistencias', json={
                'persona_id': '1', 'nombre': 'P',
                'tipo': 'entrada' if i % 2 == 0 else 'salida',
                'metodo': 'huella'
            })
        resp = client.get('/api/asistencias',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3
        for a in data:
            assert 'id' in a
            assert 'persona_id' in a
            assert 'tipo' in a
            assert 'metodo' in a
            assert 'fecha_hora' in a
            assert 'sincronizado' in a

    def test_asistencia_metodo_default(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '33.333.333-3'})
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'salida'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_listar_empleador_solo_su_empresa(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'AdminP', 'rut': '44.444.444-4'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'AdminP', 'tipo': 'entrada', 'metodo': 'huella'
        })
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'EmpP', 'rut': '44.444.444-5'})
        client.post('/api/asistencias', json={
            'persona_id': '2', 'nombre': 'EmpP', 'tipo': 'entrada', 'metodo': 'facial'
        })
        resp = client.get('/api/asistencias',
            headers={'Authorization': f'Bearer {empleador_token}'})
        data = resp.get_json()
        for a in data:
            assert a['nombre'] != 'AdminP'

    def test_sync_asistencias(self, client, admin_token, mock_thread):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P1', 'rut': '55.555.555-1'})
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P2', 'rut': '55.555.555-2'})
        resp = client.post('/api/asistencias/sync', json={
            'registros': [
                {'persona_id': '1', 'nombre': 'P1', 'tipo': 'entrada', 'metodo': 'huella'},
                {'persona_id': '2', 'nombre': 'P2', 'tipo': 'entrada', 'metodo': 'facial'},
                {'persona_id': '1', 'nombre': 'P1', 'tipo': 'salida', 'metodo': 'huella'},
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['insertados'] == 3
        assert data['errores'] == 0

    def test_sync_sin_registros(self, client):
        resp = client.post('/api/asistencias/sync', json={'registros': []})
        assert resp.status_code == 200
        assert resp.get_json()['insertados'] == 0

    def test_asistencia_sin_persona_id(self, client):
        resp = client.post('/api/asistencias', json={
            'nombre': 'Anon', 'tipo': 'entrada'
        })
        assert resp.status_code == 200  # should work without persona_id

    def test_erp_push_se_dispara(self, client, admin_token, mock_thread, mock_requests_post):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '66.666.666-6'})
        client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP Test', 'tipo': 'generic',
                'webhook_url': 'http://fake-webhook.test/api/marcajes',
                'headers': '{}', 'field_map': '{}', 'envio_auto': True
            })
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada', 'metodo': 'facial'
        })
        assert resp.status_code == 200
        mock_thread.assert_called()


class TestRoutesDispositivos:
    """Tests para /api/dispositivos — CRUD, verificacion, ERP config."""

    def test_listar_dispositivos_vacio(self, client):
        resp = client.get('/api/dispositivos')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_listar_dispositivos_admin(self, client, admin_token):
        resp = client.get('/api/dispositivos',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_delete_dispositivo_sin_auth(self, client):
        resp = client.delete('/api/dispositivos/999')
        assert resp.status_code == 401

    def test_update_dispositivo_admin(self, client, admin_token):
        client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Test Dev'})
        resp = client.put('/api/dispositivos/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Renamed'})
        assert resp.status_code == 200
        assert resp.get_json()['nombre'] == 'Renamed'

    def test_update_sin_nombre(self, client, admin_token):
        resp = client.put('/api/dispositivos/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 400

    def test_verificar_dispositivo_exito(self, client, admin_token, mock_requests_get):
        mock_requests_get.return_value.status_code = 200
        mock_requests_get.return_value.headers = {'content-type': 'application/json'}
        mock_requests_get.return_value.json.return_value = {
            'mac': 'AA:BB:CC:DD:EE:FF', 'ssid': 'WiFi-Empresa', 'enrolado': True
        }
        resp = client.post('/api/dispositivos/verificar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'ip': '192.168.1.100'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_verificar_dispositivo_connection_error(self, client, admin_token, mock_requests_get):
        import requests as req
        mock_requests_get.side_effect = req.ConnectionError
        resp = client.post('/api/dispositivos/verificar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'ip': '10.0.0.99'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is False

    def test_verificar_dispositivo_sin_ip(self, client, admin_token):
        resp = client.post('/api/dispositivos/verificar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 400

    def test_erp_config_dispositivo(self, client, admin_token):
        client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP', 'tipo': 'odoo',
                'webhook_url': 'http://odoo.test/api',
                'headers': '{}', 'field_map': '{}', 'envio_auto': True, 'activo': True
            })
        resp = client.get('/api/dispositivos/erp-config',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200


class TestRoutesErp:
    """Tests para /api/erp — integraciones ERP."""

    def test_listar_erp_admin(self, client, admin_token):
        resp = client.get('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_crear_erp_generic(self, client, admin_token):
        resp = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Webhook Test', 'tipo': 'generic',
                'webhook_url': 'https://hooks.example.com/marcajes',
                'headers': '{"Content-Type":"application/json"}',
                'field_map': '{"persona_id":"employee_id","tipo":"event"}',
                'envio_auto': True
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'id' in data

    def test_delete_erp_admin(self, client, admin_token):
        c = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP X', 'tipo': 'generic',
                'webhook_url': 'http://test.com', 'envio_auto': True
            })
        resp = client.delete(f"/api/erp/{c.get_json()['id']}",
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_empleador_solo_ve_sus_erps(self, client, admin_token, empleador_token):
        client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Admin ERP', 'tipo': 'generic',
                'webhook_url': 'http://a.test', 'envio_auto': True
            })
        resp = client.get('/api/erp',
            headers={'Authorization': f'Bearer {empleador_token}'})
        for erp in resp.get_json():
            assert erp['nombre'] != 'Admin ERP'

    def test_test_webhook_exitoso(self, client, admin_token, mock_requests_post):
        mock_requests_post.return_value.status_code = 200
        mock_requests_post.return_value.ok = True
        mock_requests_post.return_value.text = '{"status":"ok"}'
        c = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Testable', 'tipo': 'generic',
                'webhook_url': 'http://fake.test', 'envio_auto': True
            })
        resp = client.post(f"/api/erp/{c.get_json()['id']}/test",
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_erp_estado(self, client, admin_token):
        c = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Statusable', 'tipo': 'generic',
                'webhook_url': 'http://fake.test', 'envio_auto': True
            })
        resp = client.get(f"/api/erp/{c.get_json()['id']}/estado",
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_erp_enviar_manual(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.100.100-0'})
        client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada', 'metodo': 'huella'
        })
        c = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'BatchEnviar', 'tipo': 'generic',
                'webhook_url': 'http://fake.test', 'envio_auto': False
            })
        resp = client.post(f"/api/erp/{c.get_json()['id']}/enviar",
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_transformar_datos_static(self, client):
        from routes.erp import _transformar_datos
        datos = {'persona_id': '42', 'nombre': 'Juan', 'tipo': 'entrada'}
        field_map = '{"persona_id":"employee_id","tipo":"event_type"}'
        result = _transformar_datos(datos, field_map)
        assert result['employee_id'] == '42'
        assert result['event_type'] == 'entrada'
        assert result['nombre'] == 'Juan'

    def test_enviar_a_webhook_failure(self, mock_requests_post):
        import requests as req
        mock_requests_post.side_effect = req.ConnectionError
        from routes.erp import _enviar_a_webhook
        result = _enviar_a_webhook('http://offline.test', '{}', {'test': True})
        assert result['ok'] is False
        assert 'error' in result
