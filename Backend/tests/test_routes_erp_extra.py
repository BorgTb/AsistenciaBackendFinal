"""Tests adicionales para routes/erp.py.

Cubre ramas sin ejercitar por los tests existentes (test_routes_sync_erp.py):
helpers internos (_fmt_chile, _enviar_a_webhook excepcion generica,
_guardar_estado_envio con error, enviar_asistencia_a_erps), y ramas de
autorizacion/error de los endpoints (empleador vs admin, recursos
inexistentes, empresa no identificada).
"""
from unittest.mock import MagicMock, patch
import datetime


class TestFmtChile:
    def test_fmt_chile_valor_vacio(self):
        from routes.erp import _fmt_chile
        assert _fmt_chile(None) == ''
        assert _fmt_chile('') == ''

    def test_fmt_chile_string_se_retorna_igual(self):
        from routes.erp import _fmt_chile
        assert _fmt_chile('2025-01-01T00:00:00') == '2025-01-01T00:00:00'

    def test_fmt_chile_datetime_naive_se_formatea(self):
        from routes.erp import _fmt_chile
        dt = datetime.datetime(2025, 6, 1, 10, 30, 0)
        resultado = _fmt_chile(dt)
        assert resultado.startswith('2025-06-01')


class TestEnviarAWebhookExcepcionGenerica:
    def test_enviar_a_webhook_excepcion_generica(self, mocker):
        from routes.erp import _enviar_a_webhook
        mocker.patch('requests.post', side_effect=ValueError('payload invalido'))
        resultado = _enviar_a_webhook('http://erp.test/hook', '{}', {'x': 1})
        assert resultado['ok'] is False
        assert 'payload invalido' in resultado['error']


class TestGuardarEstadoEnvioError:
    def test_guardar_estado_envio_excepcion_hace_rollback(self):
        from routes.erp import _guardar_estado_envio
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('update fallo')
        with patch('routes.erp.get_connection', return_value=mock_conn):
            _guardar_estado_envio(1, {'ok': False, 'error': 'fallo'})
        mock_conn.rollback.assert_called_once()
        mock_cur.close.assert_called_once()
        mock_conn.close.assert_called_once()


class TestEnviarAsistenciaAErps:
    """Cubre enviar_asistencia_a_erps (lineas 74-109), que no tenia
    ningun test directo: solo se invocaba indirectamente desde el flujo
    real de marcaje, nunca verificando su comportamiento end-to-end."""

    def test_enviar_asistencia_a_erps_sin_integraciones(self, app, client, admin_token):
        from routes.erp import enviar_asistencia_a_erps
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Sin ERP', 'rut': '21.000.000-1'})
        persona_id = p.get_json()['id']

        resultados = enviar_asistencia_a_erps(
            persona_id, 'Sin ERP', 'entrada', 'huella',
            datetime.datetime.now(), empresa_id=1)
        assert resultados == []

    def test_enviar_asistencia_a_erps_con_integracion_activa(self, app, client, admin_token, mock_requests_post):
        from routes.erp import enviar_asistencia_a_erps
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Con ERP', 'rut': '21.000.000-2'})
        persona_id = p.get_json()['id']

        client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ERP1', 'webhook_url': 'http://erp.test/hook',
                  'envio_auto': True, 'activo': True})

        mock_requests_post.return_value.ok = True
        resultados = enviar_asistencia_a_erps(
            persona_id, 'Con ERP', 'entrada', 'huella',
            datetime.datetime.now(), empresa_id=1)
        assert len(resultados) == 1
        assert resultados[0]['resultado']['ok'] is True

    def test_enviar_asistencia_a_erps_sin_persona_id(self, app, admin_token, client, mock_requests_post):
        from routes.erp import enviar_asistencia_a_erps
        client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ERP2', 'webhook_url': 'http://erp.test/hook2',
                  'envio_auto': True, 'activo': True})
        resultados = enviar_asistencia_a_erps(
            None, 'Anonimo', 'entrada', 'huella',
            datetime.datetime.now(), empresa_id=1)
        assert len(resultados) == 1


class TestErpAutorizacionYErrores:

    def test_create_erp_sin_empresa_id(self, app):
        """request.empresa_id puede ser None (linea 193). Se llama a la
        funcion de vista directamente (sin el decorador @requiere_rol) para
        aislar esta rama, ya que los fixtures de login siempre asignan una
        empresa al usuario admin/empleador."""
        from routes.erp import create_erp
        with app.test_request_context('/api/erp', method='POST',
                                       json={'nombre': 'X', 'webhook_url': 'http://x'}):
            from flask import request as flask_request
            flask_request.empresa_id = None
            flask_request.user_rol = 'admin'
            resp = create_erp()
            assert resp[1] == 401

    def test_create_erp_headers_y_fieldmap_como_dict(self, client, admin_token):
        resp = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'ERP Dict', 'webhook_url': 'http://erp.test/dict',
                'headers': {'Authorization': 'Bearer xyz'},
                'field_map': {'rut': 'employee_id'}
            })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_delete_erp_empleador_su_empresa(self, client, empleador_token):
        crear = client.post('/api/erp',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'ERP Empleador', 'webhook_url': 'http://erp.test/emp'})
        erp_id = crear.get_json()['id']
        resp = client.delete(f'/api/erp/{erp_id}',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_delete_erp_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.erp.get_connection', return_value=mock_conn):
            resp = client.delete('/api/erp/1',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()

    def test_test_erp_empleador_erp_de_otra_empresa(self, client, admin_token, empleador_token):
        crear = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ERP Admin', 'webhook_url': 'http://erp.test/admin'})
        erp_id = crear.get_json()['id']
        resp = client.post(f'/api/erp/{erp_id}/test',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 404

    def test_test_erp_admin_erp_inexistente(self, client, admin_token):
        resp = client.post('/api/erp/99999/test',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_enviar_erp_empleador_erp_de_otra_empresa(self, client, admin_token, empleador_token):
        crear = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ERP Admin2', 'webhook_url': 'http://erp.test/admin2'})
        erp_id = crear.get_json()['id']
        resp = client.post(f'/api/erp/{erp_id}/enviar',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 404

    def test_enviar_erp_admin_erp_inexistente(self, client, admin_token):
        resp = client.post('/api/erp/99999/enviar',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_enviar_erp_con_asistencias_exitosas(self, client, admin_token, mock_requests_post):
        mock_requests_post.return_value.ok = True
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Asist ERP', 'rut': '23.000.000-1'})
        client.post('/api/asistencias',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': '1', 'tipo': 'entrada', 'metodo': 'manual'})
        crear = client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ERP Exitoso', 'webhook_url': 'http://erp.test/exitoso'})
        erp_id = crear.get_json()['id']

        resp = client.post(f'/api/erp/{erp_id}/enviar',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enviados'] == 1
        assert data['errores'] == 0

    def test_estado_erp_empleador(self, client, empleador_token):
        crear = client.post('/api/erp',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'ERP Estado', 'webhook_url': 'http://erp.test/estado'})
        erp_id = crear.get_json()['id']
        resp = client.get(f'/api/erp/{erp_id}/estado',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200
        assert 'ultimoEstado' in resp.get_json()

    def test_erp_config_dispositivo_sin_empresa_id(self, client):
        resp = client.get('/api/dispositivos/erp-config')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_erp_config_dispositivo_con_empresa_id(self, client, admin_token):
        client.post('/api/erp',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ERP Config', 'webhook_url': 'http://erp.test/config'})
        resp = client.get('/api/dispositivos/erp-config',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)
