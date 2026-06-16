"""
Emula heartbeat y watchdog del ESP32.
Referencia: esp32.ino loop (heartbeat cada 30s) + mqtt_handler.py:85-109, 237-283
"""
import json
from unittest.mock import MagicMock


class TestEmuladorHeartbeatWatchdog:
    """Simula heartbeat y watchdog del ESP32."""

    def test_heartbeat_activa_dispositivo(self, client, admin_token):
        from mqtt_handler import on_message
        import mqtt_handler

        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP-HB'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin, 'mac': 'DE:AD:BE:EF:00:01', 'ip': '192.168.1.99'})

        mqtt_handler.heartbeat_times.clear()
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/heartbeat/DEADBEEF0001'
        mock_msg.payload = json.dumps({'ip': '192.168.1.100'}).encode()

        on_message(MagicMock(), None, mock_msg)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT estado, ip_local FROM dispositivos WHERE mac_address = 'DE:AD:BE:EF:00:01'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row[0] == 'activo'
        assert row[1] == '192.168.1.100'

    def test_lwt_marca_inactivo(self, client, admin_token):
        from mqtt_handler import on_message

        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP-LWT'})
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin_resp.get_json()['pin'],
                  'mac': 'BA:AD:F0:0D:00:01', 'ip': '10.0.0.1'})

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/lwt/BAADF00D0001'
        mock_msg.payload = b''

        on_message(MagicMock(), None, mock_msg)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT estado FROM dispositivos WHERE mac_address = 'BA:AD:F0:0D:00:01'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row[0] == 'inactivo'

    def test_heartbeat_sin_ip_no_pierde_estado(self, client, admin_token):
        from mqtt_handler import on_message
        import mqtt_handler

        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ESP-NoIP'})
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'codigo': pin_resp.get_json()['pin'],
                  'mac': 'C0:FF:EE:00:00:01', 'ip': '192.168.1.1'})

        mqtt_handler.heartbeat_times.clear()
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/heartbeat/C0FFEE000001'
        mock_msg.payload = b'{}'

        on_message(MagicMock(), None, mock_msg)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT estado FROM dispositivos WHERE mac_address = 'C0:FF:EE:00:00:01'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row[0] == 'activo'
