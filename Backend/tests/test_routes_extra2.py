import json
from unittest.mock import patch, MagicMock


class TestAuthExtra:
    """Cubre errores y edge cases restantes en auth.py"""

    def test_me_token_expirado_mensaje(self, client):
        import jwt
        import datetime
        from app import app
        with app.app_context():
            payload = {
                'user_id': 1, 'empresa_id': 1, 'rol': 'admin',
                'exp': datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
            }
            expired_token = jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')
        resp = client.get('/api/auth/me',
            headers={'Authorization': f'Bearer {expired_token}'})
        assert resp.status_code == 401

    def test_crear_empresa_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.post('/api/auth/empresas',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={
                    'nombre': 'Test Empresa',
                    'mode': 'new',
                    'nombre_usuario': 'Test User',
                    'email_usuario': 'test@test.cl',
                    'password_usuario': 'test1234',
                })
            assert resp.status_code == 500

    def test_enrolar_pin_invalido_404(self, client):
        resp = client.post('/api/auth/dispositivos/enrolar', json={
            'codigo': 'INVALIDO', 'mac': 'AA:BB:CC:DD:EE:99'
        })
        assert resp.status_code == 404

    def test_generar_pin_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.post('/api/auth/dispositivos/generar-pin',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'nombre': 'Test'})
            assert resp.status_code == 500

    def test_asignar_usuario_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.post('/api/auth/asignar-usuario',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'usuario_id': 1, 'empresa_id': 1, 'rol': 'empleador'})
            assert resp.status_code == 500

    def test_solicitar_eliminacion_db_error(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Test', 'rut': '11.111.111-1', 'email': 'test@test.cl'})
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.post('/api/auth/solicitar-eliminacion-datos', json={
                'rut': '11.111.111-1', 'email': 'test@test.cl', 'nombre': 'Test'
            })
            assert resp.status_code == 500


class TestErpExtra:
    """Cubre mascaras de configuracion ERP y field mapping"""

    def test_crear_erp_con_mascaras_por_defecto(self, client, admin_token):
        resp = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP Test',
                'tipo': 'otro',
                'webhook_url': 'http://test.com/webhook',
                'headers': json.dumps({'token_api': 'tok123', 'tipo_auth': 'bearer'}),
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_crear_erp_sin_token_api(self, client, admin_token):
        resp = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP Sin Token',
                'tipo': 'otro',
                'webhook_url': 'http://test.com/webhook',
            })
        assert resp.status_code == 200

    def test_crear_erp_odoo_con_mascaras(self, client, admin_token):
        resp = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP Odoo',
                'tipo': 'odoo',
                'webhook_url': 'http://odoo.com/webhook',
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_erp_transformar_con_json_invalido(self, client, admin_token):
        resp = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP Map OK',
                'tipo': 'otro',
                'webhook_url': 'http://test.com/hook',
                'field_map': '{"campo": "valor"}',
            })
        assert resp.status_code == 200

    def test_erp_crear_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.erp.get_connection', return_value=mock_conn):
            resp = client.post('/api/erp',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'nombre': 'X', 'tipo': 'otro', 'webhook_url': 'http://x.com'})
            assert resp.status_code == 500


class TestAsistenciasExtra2:
    """Cubre dispatch y error paths en asistencias.py"""

    def test_create_asistencia_persona_id_int(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '70.111.111-1'})
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_create_asistencia_con_rut(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '70.111.111-2'})
        resp = client.post('/api/asistencias', json={
            'rut': '70.111.111-2', 'nombre': 'P', 'tipo': 'salida'
        })
        assert resp.status_code == 200

    def test_create_asistencia_db_error(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '70.111.111-3'})
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.asistencias.get_connection', return_value=mock_conn):
            resp = client.post('/api/asistencias', json={
                'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
            })
            assert resp.status_code == 500

    def test_erp_push_async_disabled(self, client, admin_token):
        import os
        os.environ['DISABLE_ASYNC_DISPATCH'] = '1'
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '70.111.111-4'})
        resp = client.post('/api/asistencias', json={
            'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'
        })
        assert resp.status_code == 200

    def test_sync_asistencias_sin_data(self, client, admin_token):
        resp = client.post('/api/asistencias/sync', json={'registros': []})
        assert resp.status_code == 200

    def test_sync_asistencias_sin_token(self, client):
        client.post('/api/personas', json={
            'nombre': 'P', 'rut': '70.111.111-5'
        })
        resp = client.post('/api/asistencias/sync', json={
            'registros': [{'persona_id': '1', 'nombre': 'P', 'tipo': 'entrada'}]
        })
        assert resp.status_code == 200

    def test_sync_asistencias_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.asistencias.get_connection', return_value=mock_conn):
            resp = client.post('/api/asistencias/sync',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'registros': [{'persona_id': '1', 'tipo': 'entrada'}]})
            assert resp.status_code == 500


class TestDispositivosExtra2:
    """Cubre errores en dispositivos.py"""

    def test_eliminar_password_dispositivo_inexistente(self, client, admin_token):
        resp = client.delete('/api/dispositivos/99999/password',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_registrar_huella_sin_persona_id(self, client, admin_token):
        resp = client.post('/api/dispositivos/1/registrar-huella',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 400


class TestPersonasExtra2:
    """Cubre edge cases en personas.py"""

    def test_update_persona_parcial(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Original', 'rut': '80.111.111-2', 'email': 'orig@test.cl'})
        resp = client.put('/api/personas/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Actualizado'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_update_persona_email_invalido_caracter(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '80.111.111-3', 'email': 'valido@test.cl'})
        resp = client.put('/api/personas/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'email': 'sin-arroba'})
        assert resp.status_code == 400

    def test_create_persona_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.post('/api/personas',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'nombre': 'P', 'rut': '80.111.111-1'})
            assert resp.status_code == 500

    def test_delete_persona_hard_error(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '80.111.111-4'})
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception('DB error')
        mock_conn.cursor.return_value = mock_cur
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.delete('/api/personas/1',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500
