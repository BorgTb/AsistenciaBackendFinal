"""
Emula registrarRostroEnBackend() del ESP32 via MQTT.
Referencia: esp32.ino:989-1013
"""
import io
import json
import base64
from unittest.mock import MagicMock
from PIL import Image


def _b64_jpeg():
    img = Image.new('RGB', (16, 16), (80, 120, 160))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=70)
    return base64.b64encode(buf.getvalue()).decode()


class TestEmuladorRegistroFacialMQTT:
    """Simula el envio de imagen facial via MQTT desde ESP32."""

    def test_registro_via_mqtt(self, client, admin_token):
        from mqtt_handler import on_message

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'MQTT-Face', 'rut': '40.000.000-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})

        mock_client = MagicMock()
        payload = json.dumps({
            'persona_id': '1',
            'imagen': _b64_jpeg()
        })
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/imagen/registrar'
        mock_msg.payload = payload.encode()

        on_message(mock_client, None, mock_msg)

        publish_calls = mock_client.publish.call_args_list
        assert len(publish_calls) >= 1
        resp = json.loads(publish_calls[-1][0][1])
        assert resp['status'] == 'ok'

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT encoding_facial FROM personas WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row[0] is not None

    def test_mqtt_payload_formato_correcto(self, client, admin_token):
        """Verifica que el formato del payload MQTT sea el esperado."""
        from mqtt_handler import on_message

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Formato', 'rut': '40.000.002-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})

        mock_client = MagicMock()
        payload_dict = {
            'persona_id': '1',
            'imagen': _b64_jpeg()
        }
        payload_str = json.dumps(payload_dict)  # same format ESP32 uses
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/imagen/registrar'
        mock_msg.payload = payload_str.encode()

        on_message(mock_client, None, mock_msg)
        assert mock_client.publish.called

    def test_mqtt_mensaje_incompleto_rechazado(self, client):
        from mqtt_handler import on_message

        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/imagen/registrar'
        mock_msg.payload = b'{"persona_id": ""}'

        on_message(mock_client, None, mock_msg)
        mock_client.publish.assert_not_called()
