import json
import time
from unittest.mock import MagicMock, patch, PropertyMock


class TestMqttHandlerExtra:

    def test_device_pinger_loop_continue_sin_mqtt(self):
        from mqtt_handler import device_pinger
        mock_client = MagicMock()

        with patch('mqtt_handler._mqtt_client', None), \
             patch('mqtt_handler.time.sleep', side_effect=[None, StopIteration()]), \
             patch('mqtt_handler.get_connection') as mock_conn:
            mock_cur = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cur
            mock_cur.fetchall.return_value = []
            try:
                device_pinger()
            except StopIteration:
                pass

    def test_device_pinger_con_dispositivos(self):
        from mqtt_handler import device_pinger, heartbeat_times, heartbeat_lock

        mock_client = MagicMock()

        with patch('mqtt_handler._mqtt_client', mock_client), \
             patch('mqtt_handler.time.sleep', side_effect=[None, StopIteration()]), \
             patch('mqtt_handler.get_connection') as mock_conn:
            mock_cur = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cur
            mock_cur.fetchall.return_value = [('AABBCCDDEE01',)]
            try:
                device_pinger()
            except StopIteration:
                pass
            mock_client.publish.assert_called()

    def test_device_pinger_marca_vencidos(self):
        from mqtt_handler import device_pinger, heartbeat_times, heartbeat_lock

        mock_client = MagicMock()
        with heartbeat_lock:
            heartbeat_times['AABBCCDDEE99'] = 0

        with patch('mqtt_handler._mqtt_client', mock_client), \
             patch('mqtt_handler.time.sleep', side_effect=[None, StopIteration()]), \
             patch('mqtt_handler.time.time', return_value=999999), \
             patch('mqtt_handler.get_connection') as mock_conn:
            mock_cur = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cur
            mock_cur.fetchall.return_value = [('AABBCCDDEE01',)]
            mock_cur.fetchone.return_value = (42, 'DeviceVencido', '', 'inactivo')
            try:
                device_pinger()
            except StopIteration:
                pass

        with heartbeat_lock:
            heartbeat_times.clear()

    def test_start_mqtt_secure_mode(self):
        from mqtt_handler import start_mqtt
        with patch('mqtt_handler.SECURE_MODE', True), \
             patch('mqtt_handler.mqtt.Client') as mock_client_class, \
             patch('mqtt_handler.threading.Thread') as mock_thread:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance
            result = start_mqtt(broadcast_callback=lambda x: None)
            assert result is not None
            mock_instance.tls_set.assert_called_once()
            mock_instance.tls_insecure_set.assert_called_once_with(True)

    def test_start_mqtt_insecure_mode(self):
        from mqtt_handler import start_mqtt
        with patch('mqtt_handler.SECURE_MODE', False), \
             patch('mqtt_handler.mqtt.Client') as mock_client_class, \
             patch('mqtt_handler.threading.Thread'):
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance
            result = start_mqtt(broadcast_callback=lambda x: None)
            assert result is not None
            mock_instance.connect.assert_called_once()
            mock_instance.loop_start.assert_called_once()

    def test_start_mqtt_with_password(self):
        from mqtt_handler import start_mqtt
        with patch('mqtt_handler.SECURE_MODE', False), \
             patch('mqtt_handler.MQTT_PASSWORD', 'secret'), \
             patch('mqtt_handler.mqtt.Client') as mock_client_class, \
             patch('mqtt_handler.threading.Thread'):
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance
            start_mqtt()
            mock_instance.username_pw_set.assert_called_once_with('sas', 'secret')

    def test_start_mqtt_exception_retorna_none(self):
        from mqtt_handler import start_mqtt
        with patch('mqtt_handler.mqtt.Client', side_effect=Exception('boom')):
            result = start_mqtt()
            assert result is None

    def test_on_message_imagen_eco(self):
        from mqtt_handler import on_message
        mock_client = MagicMock()
        msg = MagicMock()
        msg.topic = 'esp32/imagen/eco'
        msg.payload = b''
        on_message(mock_client, None, msg)

    def test_enviar_comando_sin_mqtt(self):
        from mqtt_handler import enviar_comando_dispositivo
        with patch('mqtt_handler._mqtt_client', None):
            result = enviar_comando_dispositivo('AABBCCDDEE01', 'reiniciar')
            assert result is False

    def test_enviar_comando_con_mqtt(self):
        from mqtt_handler import enviar_comando_dispositivo
        mock_client = MagicMock()
        with patch('mqtt_handler._mqtt_client', mock_client):
            result = enviar_comando_dispositivo('AABBCCDDEE01', 'sync')
            assert result is True
            mock_client.publish.assert_called_once()

    def test_broadcast_device_update_con_callback(self):
        from mqtt_handler import broadcast_device_update
        callback = MagicMock()
        with patch('mqtt_handler._broadcast_callback', callback):
            broadcast_device_update({'test': True})
            callback.assert_called_once_with({'test': True})

    def test_broadcast_device_update_sin_callback(self):
        from mqtt_handler import broadcast_device_update
        with patch('mqtt_handler._broadcast_callback', None):
            broadcast_device_update({'test': True})

    def test_broadcast_callback_exception(self):
        from mqtt_handler import broadcast_device_update
        callback = MagicMock(side_effect=Exception('fail'))
        with patch('mqtt_handler._broadcast_callback', callback):
            broadcast_device_update({'test': True})

    def test_device_watchdog_initial_sweep(self):
        from mqtt_handler import device_watchdog
        with patch('mqtt_handler.get_connection') as mock_conn, \
             patch('mqtt_handler.time.sleep', side_effect=[StopIteration()]):
            mock_cur = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cur
            try:
                device_watchdog()
            except StopIteration:
                pass
            mock_cur.execute.assert_any_call(
                "UPDATE dispositivos SET estado = 'inactivo' WHERE mac_address IS NOT NULL AND mac_address != ''"
            )
