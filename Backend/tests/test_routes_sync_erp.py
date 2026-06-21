def _enrolar_dispositivo(client, token, nombre='Test', mac='AA:BB:CC:DD:EE:01', ip='192.168.1.10'):
    pin_resp = client.post('/api/auth/dispositivos/generar-pin',
        headers={'Authorization': f'Bearer {token}'},
        json={'nombre': nombre})
    pin = pin_resp.get_json()['pin']
    enrol_resp = client.post('/api/auth/dispositivos/enrolar', json={
        'codigo': pin, 'mac': mac, 'ip': ip
    })
    return enrol_resp.get_json()['dispositivo_id']


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

    def test_listar_asistencias_trabajador(self, client, trabajador_token):
        resp = client.get('/api/asistencias',
            headers={'Authorization': f'Bearer {trabajador_token}'})
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_sync_con_duplicados(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '99.999.999-1'})
        payload = {'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada', 'metodo': 'huella'}
        r1 = client.post('/api/asistencias', json=payload)
        r2 = client.post('/api/asistencias/sync', json={'registros': [payload]})
        assert r1.status_code == 200
        assert r2.status_code == 200


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

    def test_listar_incluye_password_flags(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token)
        resp = client.get('/api/dispositivos',
            headers={'Authorization': f'Bearer {admin_token}'})
        data = resp.get_json()
        dev = next(d for d in data if d['id'] == str(dev_id))
        assert 'tiene_password' in dev
        assert 'password_pendiente' in dev
        assert dev['tiene_password'] is False
        assert dev['password_pendiente'] is False

    def test_listar_password_flags_cambian(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token)
        client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.get('/api/dispositivos',
            headers={'Authorization': f'Bearer {admin_token}'})
        data = resp.get_json()
        dev = next(d for d in data if d['id'] == str(dev_id))
        assert dev['tiene_password'] is True
        assert dev['password_pendiente'] is True

    def test_generar_password_exito(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token)
        resp = client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'password' in data
        assert len(data['password']) == 12

    def test_generar_password_no_enrolado(self, client, admin_token):
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'No enrol'})
        dev_id = pin_resp.get_json()['dispositivo_id']
        resp = client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 400
        assert 'Solo disponible' in resp.get_json()['error']

    def test_generar_password_sin_auth(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token)
        resp = client.post(f'/api/dispositivos/{dev_id}/generar-password')
        assert resp.status_code == 401

    def test_generar_password_inexistente(self, client, admin_token):
        resp = client.post('/api/dispositivos/99999/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_generar_password_sobrescribe(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token)
        r1 = client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        p1 = r1.get_json()['password']
        r2 = client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        p2 = r2.get_json()['password']
        assert p1 != p2

    def test_generar_password_empleador_otra_empresa(self, client, admin_token, empleador_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:99')
        resp = client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 404

    def test_eliminar_password_exito(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token)
        client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.delete(f'/api/dispositivos/{dev_id}/password',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_eliminar_password_sin_auth(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token)
        resp = client.delete(f'/api/dispositivos/{dev_id}/password')
        assert resp.status_code == 401

    def test_eliminar_password_inexistente(self, client, admin_token):
        resp = client.delete('/api/dispositivos/99999/password',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_check_password_pendiente_true(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:10')
        client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.get('/api/dispositivos/check-password',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:10'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['pendiente'] is True
        assert 'password' in data
        assert len(data['password']) == 12

    def test_check_password_no_pendiente(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:11')
        resp = client.get('/api/dispositivos/check-password',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:11'})
        assert resp.status_code == 200
        assert resp.get_json()['pendiente'] is False

    def test_check_password_sin_mac(self, client):
        resp = client.get('/api/dispositivos/check-password')
        assert resp.status_code == 400

    def test_check_password_mac_inexistente(self, client):
        resp = client.get('/api/dispositivos/check-password',
            headers={'X-Device-MAC': 'ZZ:ZZ:ZZ:ZZ:ZZ:ZZ'})
        assert resp.status_code == 404

    def test_confirmar_password_exito(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:20')
        client.post(f'/api/dispositivos/{dev_id}/generar-password',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.post('/api/dispositivos/confirmar-password',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:20'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        check = client.get('/api/dispositivos/check-password',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:20'})
        assert check.get_json()['pendiente'] is False

    def test_confirmar_password_sin_mac(self, client):
        resp = client.post('/api/dispositivos/confirmar-password')
        assert resp.status_code == 400

    def test_confirmar_password_mac_inexistente(self, client):
        resp = client.post('/api/dispositivos/confirmar-password',
            headers={'X-Device-MAC': 'ZZ:ZZ:ZZ:ZZ:ZZ:ZZ'})
        assert resp.status_code == 404

    def test_delete_dispositivo_exito_admin(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token)
        resp = client.delete(f'/api/dispositivos/{dev_id}',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_put_dispositivo_not_found(self, client, admin_token):
        resp = client.put('/api/dispositivos/99999',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'No existe'})
        assert resp.status_code == 404

    def test_listar_dispositivos_sin_token(self, client):
        resp = client.get('/api/dispositivos')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_listar_dispositivos_empleador(self, client, empleador_token):
        resp = client.get('/api/dispositivos',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200

    def test_delete_dispositivo_admin(self, client, admin_token):
        from unittest.mock import patch, MagicMock
        _enrolar_dispositivo(client, admin_token, 'DeleteMe', 'AA:BB:CC:DD:EE:99', '10.0.0.99')
        resp = client.delete('/api/dispositivos/1',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_delete_dispositivo_db_error(self, client, admin_token):
        from unittest.mock import patch, MagicMock
        _enrolar_dispositivo(client, admin_token, 'ErrDel', 'AA:BB:CC:DD:EE:98', '10.0.0.98')
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.dispositivos.get_connection', return_value=mock_conn):
            resp = client.delete('/api/dispositivos/1',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500

    def test_listar_dispositivos_trabajador(self, client, trabajador_token):
        resp = client.get('/api/dispositivos',
            headers={'Authorization': f'Bearer {trabajador_token}'})
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

    def test_crear_erp_sin_nombre(self, client, admin_token):
        resp = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'tipo': 'generic',
                'webhook_url': 'http://test.com',
                'envio_auto': True
            })
        assert resp.status_code == 400

    def test_test_webhook_inactivo(self, client, admin_token):
        c = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Inactivo', 'tipo': 'generic',
                'webhook_url': 'http://fake.test',
                'envio_auto': True, 'activo': False
            })
        resp = client.post(f"/api/erp/{c.get_json()['id']}/test",
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 400

    def test_enviar_erp_inactivo(self, client, admin_token):
        c = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Inactivo2', 'tipo': 'generic',
                'webhook_url': 'http://fake.test',
                'envio_auto': True, 'activo': False
            })
        resp = client.post(f"/api/erp/{c.get_json()['id']}/enviar",
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 400

    def test_enviar_erp_sin_asistencias(self, client, admin_token):
        c = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Sin data', 'tipo': 'generic',
                'webhook_url': 'http://fake.test',
                'envio_auto': True, 'activo': True
            })
        resp = client.post(f"/api/erp/{c.get_json()['id']}/enviar",
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['enviados'] == 0

    def test_transformar_datos_vacio(self):
        from routes.erp import _transformar_datos
        result = _transformar_datos({'a': 1}, None)
        assert result == {'a': 1}
        result = _transformar_datos({'a': 1}, '')
        assert result == {'a': 1}
        result = _transformar_datos({'a': 1}, '{}')
        assert result == {'a': 1}

    def test_transformar_datos_json_invalido(self):
        from routes.erp import _transformar_datos
        result = _transformar_datos({'a': 1}, 'not-json')
        assert result == {'a': 1}

    def test_transformar_datos_mapping(self):
        from routes.erp import _transformar_datos
        result = _transformar_datos(
            {'nombre': 'Juan', 'rut': '11-1'},
            '{"nombre": "name", "rut": "tax_id"}'
        )
        assert result['name'] == 'Juan'
        assert result['tax_id'] == '11-1'

    def test_enviar_a_webhook_headers_json_invalido(self):
        from routes.erp import _enviar_a_webhook
        result = _enviar_a_webhook(
            'http://fake.test', 'bad-json', {'test': 1}, timeout=1
        )
        assert result['ok'] is False

    def test_enviar_a_webhook_connection_error(self, mocker):
        from routes.erp import _enviar_a_webhook
        mock_post = mocker.patch('routes.erp.requests.post')
        mock_post.side_effect = __import__('requests').ConnectionError()
        result = _enviar_a_webhook(
            'http://fake.test', None, {'test': 1}, timeout=1
        )
        assert result['ok'] is False
        assert 'No se pudo conectar' in result['error']

    def test_enviar_a_webhook_timeout(self, mocker):
        from routes.erp import _enviar_a_webhook
        mock_post = mocker.patch('routes.erp.requests.post')
        mock_post.side_effect = __import__('requests').Timeout()
        result = _enviar_a_webhook(
            'http://fake.test', None, {'test': 1}, timeout=1
        )
        assert result['ok'] is False
        assert 'Timeout' in result['error']
