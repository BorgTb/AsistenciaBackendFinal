"""Tests para eventos_mqtt.py — notificar_sincronizacion via MQTT."""
import json
from unittest.mock import MagicMock, patch


def _set_mqtt_client():
    import mqtt_handler
    mqtt_handler._mqtt_client = MagicMock()
    return mqtt_handler._mqtt_client


class TestEventosMQTT:
    def test_notificar_sincronizacion_publica_mensaje(self, app, client, admin_token):
        _set_mqtt_client()
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP-EVT'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:11', 'ip': '10.0.0.1'})

        from eventos_mqtt import notificar_sincronizacion
        notificar_sincronizacion(empresa_id=1, tipo='personas', accion='crear', registro_id=1)

        import mqtt_handler
        assert mqtt_handler._mqtt_client.publish.called
        topic = mqtt_handler._mqtt_client.publish.call_args[0][0]
        assert topic.startswith('backend/notificacion/')

    def test_notificar_sincronizacion_sin_dispositivos(self, app):
        _set_mqtt_client()
        from eventos_mqtt import notificar_sincronizacion
        notificar_sincronizacion(empresa_id=999, tipo='personas', accion='crear')
        import mqtt_handler
        mqtt_handler._mqtt_client.publish.assert_not_called()

    def test_notificar_sincronizacion_mqtt_no_disponible(self, app):
        import mqtt_handler
        mqtt_handler._mqtt_client = None
        from eventos_mqtt import notificar_sincronizacion
        notificar_sincronizacion(empresa_id=1, tipo='personas', accion='crear')

    def test_notificar_sincronizacion_con_empresa_id_nulo_y_registro_id(self, app, client, admin_token):
        _set_mqtt_client()
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP-EVT2'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:22', 'ip': '10.0.0.2'})
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P-EVT', 'rut': '77.777.777-7'})
        from eventos_mqtt import notificar_sincronizacion
        notificar_sincronizacion(empresa_id=None, tipo='personas', accion='actualizar', registro_id=1)
        import mqtt_handler
        assert mqtt_handler._mqtt_client.publish.called

    def test_notificar_sincronizacion_tipo_turnos_con_empresa_nula(self, app, client, admin_token):
        _set_mqtt_client()
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP-TURNOS'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:88', 'ip': '10.0.0.1'})
        import mqtt_handler
        mqtt_handler._mqtt_client.reset_mock()
        client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-Turno', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        mqtt_handler._mqtt_client.reset_mock()
        from eventos_mqtt import notificar_sincronizacion
        notificar_sincronizacion(empresa_id=None, tipo='turnos', accion='actualizar', registro_id=1)
        assert mqtt_handler._mqtt_client.publish.called

    def test_notificar_sincronizacion_tipo_asignaciones_con_empresa_nula(self, app, client, admin_token):
        _set_mqtt_client()
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP-ASIG'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:89', 'ip': '10.0.0.1'})
        import mqtt_handler
        mqtt_handler._mqtt_client.reset_mock()
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P-EVT', 'rut': '88.888.888-8'})
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-Asig', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': '1', 'turno_id': str(t.get_json()['id'])})
        mqtt_handler._mqtt_client.reset_mock()
        from eventos_mqtt import notificar_sincronizacion
        notificar_sincronizacion(empresa_id=None, tipo='asignaciones', accion='crear', registro_id=1)
        assert mqtt_handler._mqtt_client.publish.called

    def test_notificar_sincronizacion_publish_error_ignored(self, app, client, admin_token):
        mock_client = _set_mqtt_client()
        mock_client.publish.side_effect = Exception('MQTT error')
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP-ERR'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:33', 'ip': '10.0.0.3'})
        from eventos_mqtt import notificar_sincronizacion
        notificar_sincronizacion(empresa_id=1, tipo='personas', accion='crear')
        assert mock_client.publish.called
