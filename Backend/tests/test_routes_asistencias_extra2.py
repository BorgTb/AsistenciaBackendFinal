"""Tests adicionales para routes/asistencias.py.

Cubre: el envio asincrono real de ERP/email (deshabilitado por defecto en el
entorno de test via DISABLE_ASYNC_DISPATCH=1), ramas de sincronizacion batch,
notificaciones MQTT que fallan, y ramas de error/autorizacion de
update/delete que no tenian prueba directa.
"""
import os
from unittest.mock import MagicMock, patch

import pytest


def _enrolar_dispositivo(client, token, nombre='Test2', mac='AA:BB:CC:DD:EE:60', ip='192.168.1.60'):
    pin_resp = client.post('/api/auth/dispositivos/generar-pin',
        headers={'Authorization': f'Bearer {token}'},
        json={'nombre': nombre})
    pin = pin_resp.get_json()['pin']
    enrol_resp = client.post('/api/auth/dispositivos/enrolar', json={
        'codigo': pin, 'mac': mac, 'ip': ip
    })
    return enrol_resp.get_json()['dispositivo_id']


class TestDispatchAsincronoReal:
    """_erp_push_async y _email_async retornan temprano cuando
    DISABLE_ASYNC_DISPATCH=1 (fijado por conftest para todo el resto de la
    suite). Aqui se desactiva esa bandera puntualmente para ejercitar el
    cuerpo real de ambas funciones (lineas 14-18 y 32-35)."""

    def test_erp_push_async_retorna_temprano_si_deshabilitado(self, app, monkeypatch):
        from routes.asistencias import _erp_push_async
        monkeypatch.setenv('DISABLE_ASYNC_DISPATCH', '1')
        with patch('routes.erp.enviar_asistencia_a_erps') as mock_enviar:
            _erp_push_async(1, 'Persona', 'entrada', 'huella', None, empresa_id=1)
            mock_enviar.assert_not_called()

    def test_email_async_retorna_temprano_si_deshabilitado(self, app, monkeypatch):
        from routes.asistencias import _email_async
        monkeypatch.setenv('DISABLE_ASYNC_DISPATCH', '1')
        with patch('routes.asistencias.enviar_notificacion_marcacion') as mock_email:
            _email_async('persona@test.cl', 'Persona', 'entrada', None)
            mock_email.assert_not_called()

    def test_erp_push_async_intenta_enviar(self, app, monkeypatch):
        from routes.asistencias import _erp_push_async
        monkeypatch.delenv('DISABLE_ASYNC_DISPATCH', raising=False)
        with patch('routes.erp.enviar_asistencia_a_erps') as mock_enviar:
            _erp_push_async(1, 'Persona', 'entrada', 'huella', None, empresa_id=1)
            mock_enviar.assert_called_once()

    def test_erp_push_async_excepcion_no_rompe(self, app, monkeypatch):
        from routes.asistencias import _erp_push_async
        monkeypatch.delenv('DISABLE_ASYNC_DISPATCH', raising=False)
        with patch('routes.erp.enviar_asistencia_a_erps', side_effect=Exception('fallo erp')):
            _erp_push_async(1, 'Persona', 'entrada', 'huella', None, empresa_id=1)

    def test_email_async_intenta_enviar(self, app, monkeypatch):
        from routes.asistencias import _email_async
        monkeypatch.delenv('DISABLE_ASYNC_DISPATCH', raising=False)
        with patch('routes.asistencias.enviar_notificacion_marcacion') as mock_email:
            _email_async('persona@test.cl', 'Persona', 'entrada', None)
            mock_email.assert_called_once()

    def test_email_async_excepcion_no_rompe(self, app, monkeypatch):
        from routes.asistencias import _email_async
        monkeypatch.delenv('DISABLE_ASYNC_DISPATCH', raising=False)
        with patch('routes.asistencias.enviar_notificacion_marcacion',
                   side_effect=Exception('fallo email')):
            _email_async('persona@test.cl', 'Persona', 'entrada', None)


class TestCreateAsistenciaNotificacionMqttFalla:
    def test_create_asistencia_notificar_excepcion_no_rompe(self, app, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:61', ip='10.0.0.61')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P MQTT', 'rut': '24.000.000-1'})
        with patch('eventos_mqtt.notificar_sincronizacion', side_effect=Exception('mqtt caido')):
            resp = client.post('/api/asistencias',
                headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:61'},
                json={'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'})
        assert resp.status_code == 200


class TestSyncAsistenciasRamas:

    def test_sync_resuelve_dispositivo_por_mac_header(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:62', ip='10.0.0.62')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Sync', 'rut': '24.000.000-2'})
        resp = client.post('/api/asistencias/sync',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:62'},
            json={'registros': [{'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'}]})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['insertados'] == 1
        assert data['errores'] == 0

    def test_sync_resuelve_persona_por_rut_en_registro(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:63', ip='10.0.0.63')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Rut Sync', 'rut': '24.000.000-3'})
        resp = client.post('/api/asistencias/sync',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:63'},
            json={'registros': [{'rut': '24.000.000-3', 'tipo': 'entrada', 'metodo': 'huella'}]})
        assert resp.status_code == 200
        assert resp.get_json()['insertados'] == 1

    def test_sync_dispositivo_resuelto_via_payload_sin_mac_header(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:64', ip='10.0.0.64')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Payload', 'rut': '24.000.000-4'})
        resp = client.post('/api/asistencias/sync',
            json={
                'dispositivo_id': dev_id,
                'registros': [{'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'}]
            })
        assert resp.status_code == 200
        assert resp.get_json()['insertados'] == 1

    def test_sync_notificacion_batch_excepcion_no_rompe(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:65', ip='10.0.0.65')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Batch', 'rut': '24.000.000-5'})
        with patch('eventos_mqtt.notificar_sincronizacion', side_effect=Exception('mqtt caido')):
            resp = client.post('/api/asistencias/sync',
                headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:65'},
                json={'registros': [{'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'}]})
        assert resp.status_code == 200
        assert resp.get_json()['insertados'] == 1


class TestDeviceSyncYDeleteDeviceErrores:

    def test_device_sync_dispositivo_no_encontrado(self, app):
        """request.dispositivo_id truthy pero sin fila en dispositivos
        (linea 313): se simula llamando a la funcion de vista *sin* el
        decorador @token_opcional (via __wrapped__), ya que ese decorador
        resetea request.dispositivo_id = None al invocar la version
        decorada, pisando cualquier valor que se asigne manualmente antes."""
        from routes.asistencias import device_sync_asistencias
        with app.test_request_context('/api/asistencias/device-sync'):
            from flask import request
            request.dispositivo_id = 999999
            resp, status = device_sync_asistencias.__wrapped__()
            assert status == 404

    def test_delete_device_dispositivo_no_encontrado(self, app):
        """Mismo caso de fila inexistente, pero para delete_asistencias_device
        (linea 379). Mismo motivo que el test anterior para usar __wrapped__."""
        from routes.asistencias import delete_asistencias_device
        with app.test_request_context('/api/asistencias/device', method='DELETE'):
            from flask import request
            request.dispositivo_id = 999999
            resp, status = delete_asistencias_device.__wrapped__()
            assert status == 404

    def test_delete_device_notificacion_excepcion_no_rompe(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:66', ip='10.0.0.66')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Del', 'rut': '24.000.000-6'})
        client.post('/api/asistencias',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:66'},
            json={'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'})
        with patch('eventos_mqtt.notificar_sincronizacion', side_effect=Exception('mqtt caido')):
            resp = client.delete('/api/asistencias/device',
                headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:66'})
        assert resp.status_code == 200
        assert resp.get_json()['eliminadas'] >= 1

    def test_delete_device_db_error_general(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:67', ip='10.0.0.67')
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = [None, Exception('DB error')]
        mock_cur.fetchone.return_value = (1,)
        with patch('routes.asistencias.get_connection', return_value=mock_conn):
            resp = client.delete('/api/asistencias/device',
                headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:67'})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()


class TestUpdateAsistenciaRamas:

    def test_update_dispositivo_autorizado(self, client, admin_token):
        dev_id = _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:68', ip='10.0.0.68')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P UpdDisp', 'rut': '24.000.000-7'})
        a = client.post('/api/asistencias',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:68'},
            json={'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'})
        asist_id = a.get_json()['id']

        resp = client.put(f'/api/asistencias/{asist_id}',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:68'},
            json={'tipo': 'salida'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_update_dispositivo_no_autorizado(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:69', ip='10.0.0.69')
        _enrolar_dispositivo(client, admin_token, mac='AA:BB:CC:DD:EE:70', ip='10.0.0.70')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P UpdDisp2', 'rut': '24.000.000-8'})
        a = client.post('/api/asistencias',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:69'},
            json={'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'})
        asist_id = a.get_json()['id']

        resp = client.put(f'/api/asistencias/{asist_id}',
            headers={'X-Device-MAC': 'AA:BB:CC:DD:EE:70'},
            json={'tipo': 'salida'})
        assert resp.status_code == 403

    def test_update_notificacion_excepcion_no_rompe(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P UpdNotif', 'rut': '24.000.000-9'})
        a = client.post('/api/asistencias',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'})
        asist_id = a.get_json()['id']
        with patch('eventos_mqtt.notificar_sincronizacion', side_effect=Exception('mqtt caido')):
            resp = client.put(f'/api/asistencias/{asist_id}',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'tipo': 'salida'})
        assert resp.status_code == 200

    def test_update_db_error_general(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P UpdErr', 'rut': '24.000.001-0'})
        a = client.post('/api/asistencias',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'})
        asist_id = a.get_json()['id']

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (int(asist_id), 1, None, 'P', 'entrada', 'huella')
        mock_cur.execute.side_effect = [None, Exception('DB error en update')]
        with patch('routes.asistencias.get_connection', return_value=mock_conn):
            resp = client.put(f'/api/asistencias/{asist_id}',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'tipo': 'salida'})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()


class TestDeleteAsistenciaErrorGeneral:

    def test_delete_db_error_general(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P DelErr', 'rut': '24.000.001-1'})
        a = client.post('/api/asistencias',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': '1', 'tipo': 'entrada', 'metodo': 'huella'})
        asist_id = a.get_json()['id']

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error en delete')
        with patch('routes.asistencias.get_connection', return_value=mock_conn):
            resp = client.delete(f'/api/asistencias/{asist_id}',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()
