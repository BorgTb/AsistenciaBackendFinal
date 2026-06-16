"""
Emula enviarAsistenciaAErp() del ESP32.
Referencia: esp32.ino:1268-1302 (direct push vía HTTP al webhook ERP)
"""


class TestEmuladorErpPush:
    """Simula el push directo a ERP desde el ESP32."""

    def test_erp_push_tras_asistencia(self, client, admin_token, mock_thread, mock_requests_post):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ERP-P', 'rut': '60.000.000-1'})

        client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Direct ERP', 'tipo': 'generic',
                'webhook_url': 'https://erp.empresa.cl/api/marcajes',
                'headers': '{"Authorization":"Bearer TOKEN"}',
                'field_map': '{}', 'envio_auto': True
            })

        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'ERP-P', 'tipo': 'entrada',
            'metodo': 'facial', 'origen': 'dispositivo'
        })
        assert resp.status_code == 200
        mock_thread.assert_called()

    def test_field_mapping_transform(self, client):
        from routes.erp import _transformar_datos

        datos = {'persona_id': '42', 'nombre': 'John', 'tipo': 'entrada',
                 'metodo': 'facial', 'fecha_hora': '2026-06-15T10:30:00'}
        field_map = '{"persona_id":"employee_id","tipo":"check_type"}'

        result = _transformar_datos(datos, field_map)
        assert result['employee_id'] == '42'
        assert result['check_type'] == 'entrada'
        assert result['nombre'] == 'John'
        assert result['metodo'] == 'facial'

    def test_erp_config_endpoint(self, client, admin_token):
        client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP Auto', 'tipo': 'odoo',
                'webhook_url': 'https://odoo.test/api',
                'headers': '{}', 'field_map': '{}', 'envio_auto': True, 'activo': True
            })
        resp = client.get('/api/dispositivos/erp-config',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        configs = resp.get_json()
        assert len(configs) == 1
        assert configs[0]['nombre'] == 'ERP Auto'
