import io
import json
import base64
import os
from unittest.mock import MagicMock, patch
from PIL import Image


def _b64_dummy_jpeg():
    img = Image.new('RGB', (16, 16), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    return base64.b64encode(buf.getvalue()).decode()


class TestMqttHandler:
    """Tests para mqtt_handler.py — cliente MQTT, heartbeat, procesamiento facial."""

    def test_on_connect_subscribe_called(self, mock_paho_client):
        from mqtt_handler import on_connect
        client = MagicMock()
        on_connect(client, None, None, 0)
        assert client.subscribe.call_count >= 4
        topics_called = [call[0][0] for call in client.subscribe.call_args_list]
        assert any('esp32/heartbeat/#' in t for t in topics_called)
        assert any('esp32/lwt/#' in t for t in topics_called)
        assert any('esp32/imagen/registrar' in t for t in topics_called)

    def test_on_connect_failure_does_not_subscribe(self, mock_paho_client):
        from mqtt_handler import on_connect
        client = MagicMock()
        on_connect(client, None, None, 1)
        client.subscribe.assert_not_called()

    def test_on_message_heartbeat_actualiza_db(self, app, client, admin_token):
        from mqtt_handler import on_message
        import mqtt_handler

        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP32-HB'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:FF', 'ip': '192.168.1.10'})

        mqtt_handler.heartbeat_times.clear()
        mock_mqtt_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/heartbeat/AABBCCDDEEFF'
        mock_msg.payload = json.dumps({'ip': '192.168.1.10'}).encode()

        on_message(mock_mqtt_client, None, mock_msg)

        assert 'AABBCCDDEEFF' in mqtt_handler.heartbeat_times

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT estado, ip_local FROM dispositivos WHERE REPLACE(mac_address, ':', '') = %s", ('AABBCCDDEEFF',))
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[0] == 'activo'
        assert row[1] == '192.168.1.10'

    def test_on_message_lwt_marca_inactivo(self, app, client, admin_token):
        from mqtt_handler import on_message

        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP32-LWT'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': 'FF:EE:DD:CC:BB:AA', 'ip': '10.0.0.1'})

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/lwt/FFEEDDCCBBAA'
        mock_msg.payload = b''

        on_message(MagicMock(), None, mock_msg)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT estado FROM dispositivos WHERE REPLACE(mac_address, ':', '') = %s", ('FFEEDDCCBBAA',))
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[0] == 'inactivo'

    def test_procesar_imagen_facial_con_consentimiento(self, app, client, admin_token):
        from mqtt_handler import procesar_imagen_facial

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.100.100-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})

        mock_mqtt_client = MagicMock()
        procesar_imagen_facial(mock_mqtt_client, '1', _b64_dummy_jpeg())

        publish_calls = mock_mqtt_client.publish.call_args_list
        assert len(publish_calls) >= 1
        status_msg = json.loads(publish_calls[-1][0][1])
        assert status_msg['status'] == 'ok'

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT encoding_facial FROM personas WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[0] is not None

    def test_procesar_imagen_facial_sin_consentimiento(self, app, client, admin_token):
        from mqtt_handler import procesar_imagen_facial

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.200.200-1'})

        mock_mqtt_client = MagicMock()
        procesar_imagen_facial(mock_mqtt_client, '1', _b64_dummy_jpeg())

        publish_calls = mock_mqtt_client.publish.call_args_list
        assert len(publish_calls) >= 1
        status_msg = json.loads(publish_calls[0][0][1])
        assert status_msg['status'] == 'error'
        assert 'consentimiento' in status_msg['mensaje'].lower()

    def test_procesar_imagen_facial_base64_invalido(self, app, client, admin_token):
        from mqtt_handler import procesar_imagen_facial

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.300.300-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})

        mock_mqtt_client = MagicMock()
        procesar_imagen_facial(mock_mqtt_client, '1', 'esta_no_es_imagen_valida!!!')

        publish_calls = mock_mqtt_client.publish.call_args_list
        status_msg = json.loads(publish_calls[0][0][1])
        assert status_msg['status'] == 'error'

    def test_on_message_registro_facial_completo(self, app, client, admin_token):
        from mqtt_handler import on_message

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '10.400.400-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})

        mock_client = MagicMock()
        payload = json.dumps({
            'persona_id': '1', 'imagen': _b64_dummy_jpeg()
        })
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/imagen/registrar'
        mock_msg.payload = payload.encode()

        on_message(mock_client, None, mock_msg)

        publish_calls = mock_client.publish.call_args_list
        final_message = json.loads(publish_calls[-1][0][1])
        assert final_message['status'] == 'ok'

    def test_on_message_registro_incompleto(self, app):
        from mqtt_handler import on_message
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/imagen/registrar'
        mock_msg.payload = b'{}'
        on_message(mock_client, None, mock_msg)
        mock_client.publish.assert_not_called()

    def test_on_message_eco(self, app):
        from mqtt_handler import on_message
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/imagen/eco'
        mock_msg.payload = b''
        on_message(mock_client, None, mock_msg)
        # eco doesn't publish anything

    def test_device_watchdog_sweep_inicial(self, app, client, admin_token):
        from mqtt_handler import device_watchdog
        import mqtt_handler

        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP32-WD'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': '11:22:33:44:55:66', 'ip': '10.0.0.5'})

        mqtt_handler.heartbeat_times = {'112233445566': 9999999999.0}  # far future

        with patch('time.sleep', side_effect=StopIteration):
            with patch('time.time', return_value=10000000000.0):
                try:
                    device_watchdog()
                except StopIteration:
                    pass

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT estado FROM dispositivos WHERE mac_address = '11:22:33:44:55:66'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[0] == 'inactivo'

    def test_heartbeat_persiste_dispositivo(self, app, client, admin_token):
        from mqtt_handler import on_message
        import mqtt_handler

        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP32-ACT'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': 'CA:FE:BA:BE:00:01', 'ip': '10.0.0.6'})

        mqtt_handler.heartbeat_times.clear()

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/heartbeat/CAFEBABE0001'
        mock_msg.payload = b'{}'

        on_message(MagicMock(), None, mock_msg)

        assert 'CAFEBABE0001' in mqtt_handler.heartbeat_times
