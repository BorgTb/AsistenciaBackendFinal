"""Tests adicionales para routes/dispositivos.py.

Cubre: reasignar_dispositivo (sin ningun test previo), las ramas 403 de
'dispositivo no pertenece a tu empresa' en reiniciar/wifi-reconnect (distintas
del 404 'no encontrado' ya cubierto), los bloques except externos que
dependen de mqtt_handler, y las ramas de _sync_por_tipo no autorizado /
fallback de empresa.
"""
from unittest.mock import MagicMock, patch


def _enrolar_dispositivo(client, token, nombre='DispExtra', mac='AA:BB:CC:DD:EF:01', ip='10.1.0.1'):
    pin_resp = client.post('/api/auth/dispositivos/generar-pin',
        headers={'Authorization': f'Bearer {token}'},
        json={'nombre': nombre})
    pin = pin_resp.get_json()['pin']
    enrol_resp = client.post('/api/auth/dispositivos/enrolar', json={
        'codigo': pin, 'mac': mac, 'ip': ip
    })
    return enrol_resp.get_json()['dispositivo_id']


class TestReasignarDispositivo:
    """reasignar_dispositivo no tenia ningun test (lineas 163-200 completas)."""

    def test_reasignar_exito(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:02', ip='10.1.0.2')
        crear_emp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Empresa Reasignar', 'rut_empresa': '12.345.678-9',
                'mode': 'new', 'nombre_usuario': 'Emp Reas',
                'email_usuario': 'reasignar@test.cl', 'password_usuario': 'test1234',
                'rol_usuario': 'empleador'
            })
        nueva_empresa_id = crear_emp.get_json()['id']

        resp = client.put(f'/api/dispositivos/{dev_id}/reasignar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'empresa_id': nueva_empresa_id})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['empresa_id_nueva'] == nueva_empresa_id

    def test_reasignar_sin_empresa_id(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:03', ip='10.1.0.3')
        resp = client.put(f'/api/dispositivos/{dev_id}/reasignar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 400

    def test_reasignar_dispositivo_no_encontrado(self, client, admin_token):
        resp = client.put('/api/dispositivos/99999/reasignar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'empresa_id': 1})
        assert resp.status_code == 404

    def test_reasignar_empresa_destino_no_encontrada(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:04', ip='10.1.0.4')
        resp = client.put(f'/api/dispositivos/{dev_id}/reasignar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'empresa_id': 99999})
        assert resp.status_code == 404

    def test_reasignar_solo_admin(self, client, admin_token, empleador_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:05', ip='10.1.0.5')
        resp = client.put(f'/api/dispositivos/{dev_id}/reasignar',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'empresa_id': 1})
        assert resp.status_code == 403

    def test_reasignar_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.side_effect = [
            (1, 'Disp', 1, 'EmpresaActual'), (2, 'EmpresaDestino'),
        ]
        mock_cur.execute.side_effect = [None, None, Exception('DB error')]
        with patch('routes.dispositivos.get_connection', return_value=mock_conn):
            resp = client.put('/api/dispositivos/1/reasignar',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'empresa_id': 2})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()


class TestCrossTenant403VsNotFound404:
    """reiniciar_dispositivo y wifi-reconnect tienen una verificacion
    explicita de "dispositivo no pertenece a tu empresa" (lineas 429 y 534),
    pero en la practica es inalcanzable via el flujo normal: la propia query
    SQL para no-admin ya filtra `AND empresa_id = %s`, asi que si el
    dispositivo es de otra empresa la fila nunca se devuelve (404, no 403).
    Para ejercitar esta rama defensiva hay que mockear la DB y devolver una
    fila con empresa_id distinta a la del token, sin pasar por el filtro
    real de la query."""

    def test_reiniciar_dispositivo_de_otra_empresa_403(self, client, empleador_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = ('AABBCCDDEF06', 'Disp', 999)  # empresa distinta a la del token
        with patch('routes.dispositivos.get_connection', return_value=mock_conn):
            resp = client.post('/api/dispositivos/1/reiniciar',
                headers={'Authorization': f'Bearer {empleador_token}'})
            assert resp.status_code == 403

    def test_wifi_reconnect_dispositivo_de_otra_empresa_403(self, client, empleador_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = ('AABBCCDDEF07', 'Disp', 999)
        with patch('routes.dispositivos.get_connection', return_value=mock_conn):
            resp = client.post('/api/dispositivos/1/wifi-reconnect',
                headers={'Authorization': f'Bearer {empleador_token}'})
            assert resp.status_code == 403


class TestExcepcionesExternasMqtt:
    """Cubre los bloques `except Exception` que envuelven las llamadas a
    mqtt_handler en reiniciar/wifi-reconnect/registrar-huella/sync (lineas
    403-404, 440-441, 508-509, 545-546)."""

    def test_registrar_huella_excepcion_mqtt(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Huella Exc', 'rut': '25.000.000-1'})
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:08', ip='10.1.0.8')
        with patch('mqtt_handler._mqtt_client', MagicMock(publish=MagicMock(side_effect=Exception('mqtt boom')))):
            resp = client.post(f'/api/dispositivos/{dev_id}/registrar-huella',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'persona_id': '1'})
            assert resp.status_code == 500

    def test_reiniciar_excepcion_mqtt(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:09', ip='10.1.0.9')
        with patch('mqtt_handler.enviar_comando_dispositivo', side_effect=Exception('mqtt boom')):
            resp = client.post(f'/api/dispositivos/{dev_id}/reiniciar',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500

    def test_wifi_reconnect_excepcion_mqtt(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:10', ip='10.1.0.10')
        with patch('mqtt_handler.enviar_comando_dispositivo', side_effect=Exception('mqtt boom')):
            resp = client.post(f'/api/dispositivos/{dev_id}/wifi-reconnect',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500

    def test_sync_excepcion_mqtt_tipo_todas(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:11', ip='10.1.0.11')
        with patch('mqtt_handler.enviar_comando_dispositivo', side_effect=Exception('mqtt boom')):
            resp = client.post('/api/dispositivos/sync',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500


class TestSyncAutorizacionYFallbackEmpresa:

    def test_sync_empleador_sin_empresa_id_no_autorizado(self, app):
        """Cubre la rama `else: return 401` de _sync_por_tipo (linea 474):
        un usuario sin empresa_id y que no es admin queda sin autorizacion."""
        from routes.dispositivos import sync_dispositivos
        with app.test_request_context('/api/dispositivos/sync', method='POST'):
            from flask import request
            request.user_rol = 'empleador'
            request.empresa_id = None
            resp, status = sync_dispositivos.__wrapped__()
            assert status == 401

    def test_sync_admin_usa_empresa_del_primer_dispositivo(self, app, client, admin_token):
        """Cuando un admin sincroniza un tipo especifico sin empresa propia
        asociada, se usa la empresa del primer dispositivo listado (linea 502)."""
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EF:12', ip='10.1.0.12')
        from routes.dispositivos import sync_dispositivos_por_tipo
        with patch('eventos_mqtt.notificar_sincronizacion') as mock_notif:
            with app.test_request_context('/api/dispositivos/sync/personas', method='POST'):
                from flask import request
                request.user_rol = 'admin'
                request.empresa_id = None
                resp = sync_dispositivos_por_tipo.__wrapped__('personas')
                assert resp.status_code == 200
            mock_notif.assert_called_once()
