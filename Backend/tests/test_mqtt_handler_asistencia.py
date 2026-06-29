import json
from unittest.mock import MagicMock, patch


class TestMqttHandlerAsistencia:
    """Tests para el topico esp32/asistencia/<mac> en on_message (mqtt_handler.py).

    Este bloque (resolucion de persona por rut o persona_id, deteccion de
    duplicados, insercion de asistencia y disparo de push ERP) no tenia
    cobertura: las pruebas existentes solo cubrian heartbeat, lwt, huella y eco.
    """

    def test_asistencia_persona_existente_por_rut(self, app, client, admin_token):
        from mqtt_handler import on_message

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Juan Perez', 'rut': '11.111.111-1'})

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/asistencia/AABBCCDDEE01'
        mock_msg.payload = json.dumps({
            'rut': '11.111.111-1', 'tipo': 'entrada', 'metodo': 'huella'
        }).encode()

        on_message(MagicMock(), None, mock_msg)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT tipo, metodo, origen, sincronizado FROM asistencias WHERE persona_id = "
                    "(SELECT id FROM personas WHERE rut = %s)", ('11.111.111-1',))
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[0] == 'entrada'
        assert row[1] == 'huella'
        assert row[2] == 'dispositivo'
        assert row[3] is True

    def test_asistencia_crea_persona_si_rut_no_existe(self, app, client, admin_token):
        from mqtt_handler import on_message

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/asistencia/AABBCCDDEE02'
        mock_msg.payload = json.dumps({
            'rut': '22.222.222-2', 'nombre': 'Nueva Persona',
            'tipo': 'entrada', 'metodo': 'facial'
        }).encode()

        on_message(MagicMock(), None, mock_msg)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT nombre FROM personas WHERE rut = %s", ('22.222.222-2',))
        persona = cur.fetchone()
        cur.close()
        conn.close()
        assert persona is not None
        assert persona[0] == 'Nueva Persona'

    def test_asistencia_resuelve_persona_id_sin_rut(self, app, client, admin_token):
        from mqtt_handler import on_message

        resp = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Con ID', 'rut': '33.333.333-3'})
        persona_id = resp.get_json()['id']

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/asistencia/AABBCCDDEE03'
        mock_msg.payload = json.dumps({
            'persona_id': persona_id, 'tipo': 'salida', 'metodo': 'huella'
        }).encode()

        on_message(MagicMock(), None, mock_msg)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT tipo FROM asistencias WHERE persona_id = %s", (persona_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[0] == 'salida'

    def test_asistencia_duplicada_mismo_dia_es_ignorada(self, app, client, admin_token):
        from mqtt_handler import on_message

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Duplicado', 'rut': '44.444.444-4'})

        payload = json.dumps({
            'rut': '44.444.444-4', 'tipo': 'entrada', 'metodo': 'huella'
        }).encode()

        msg1 = MagicMock(topic='esp32/asistencia/AABBCCDDEE04', payload=payload)
        msg2 = MagicMock(topic='esp32/asistencia/AABBCCDDEE04', payload=payload)

        on_message(MagicMock(), None, msg1)
        on_message(MagicMock(), None, msg2)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM asistencias WHERE persona_id = "
                    "(SELECT id FROM personas WHERE rut = %s) AND tipo = 'entrada'",
                    ('44.444.444-4',))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        assert count == 1

    def test_asistencia_con_timestamp_explicito(self, app, client, admin_token):
        from mqtt_handler import on_message

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Con Fecha', 'rut': '55.555.555-5'})

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/asistencia/AABBCCDDEE05'
        mock_msg.payload = json.dumps({
            'rut': '55.555.555-5', 'tipo': 'entrada', 'metodo': 'huella',
            'fecha_hora': '2025-01-15 08:30:00'
        }).encode()

        on_message(MagicMock(), None, mock_msg)

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT fecha_hora FROM asistencias WHERE persona_id = "
                    "(SELECT id FROM personas WHERE rut = %s)", ('55.555.555-5',))
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert str(row[0]).startswith('2025-01-15')

    def test_asistencia_sin_persona_ni_tipo_se_ignora(self, app):
        from mqtt_handler import on_message

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/asistencia/AABBCCDDEE06'
        mock_msg.payload = json.dumps({'metodo': 'huella'}).encode()

        # No debe lanzar excepcion aunque falten persona_id/rut y tipo
        on_message(MagicMock(), None, mock_msg)

    def test_asistencia_payload_invalido_no_rompe(self, app):
        from mqtt_handler import on_message

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/asistencia/AABBCCDDEE07'
        mock_msg.payload = b'esto no es json'

        # El bloque except Exception debe capturar el error de parseo
        on_message(MagicMock(), None, mock_msg)

    def test_asistencia_dispara_push_erp(self, app, client, admin_token):
        from mqtt_handler import on_message

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ERP Push', 'rut': '66.666.666-6'})

        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/asistencia/AABBCCDDEE08'
        mock_msg.payload = json.dumps({
            'rut': '66.666.666-6', 'tipo': 'entrada', 'metodo': 'facial'
        }).encode()

        with patch('routes.asistencias._disparar_erp_push') as mock_push:
            on_message(MagicMock(), None, mock_msg)
            mock_push.assert_called_once()


class TestMqttHandlerHuellaCallback:
    """Cubre el callback SSE de huella (con y sin excepcion) en on_message."""

    def test_huella_resultado_invoca_callback_sse(self, app, client, admin_token):
        from mqtt_handler import on_message
        import mqtt_handler

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Con Callback', 'rut': '77.777.777-7'})

        callback = MagicMock()
        with patch('mqtt_handler._huella_broadcast_callback', callback):
            mock_msg = MagicMock()
            mock_msg.topic = 'esp32/huella/resultado/1'
            mock_msg.payload = json.dumps({
                'persona_id': '1', 'huella_id': 9, 'status': 'ok'
            }).encode()
            on_message(MagicMock(), None, mock_msg)

        callback.assert_called_once()

    def test_huella_resultado_payload_invalido_excepcion_externa(self, app):
        """Payload no-JSON dispara el except Exception externo del bloque
        esp32/huella/resultado (lineas 236-237), distinto del except interno
        del callback SSE."""
        from mqtt_handler import on_message
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/huella/resultado/3'
        mock_msg.payload = b'no es json valido'
        on_message(MagicMock(), None, mock_msg)


class TestMqttHandlerHeartbeatYLwtErrores:
    """Cubre las ramas except de los bloques heartbeat y LWT cuando la DB falla."""

    def test_heartbeat_db_excepcion_no_rompe(self, app):
        from mqtt_handler import on_message
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/heartbeat/FFFFFFFFFFFF'
        mock_msg.payload = json.dumps({'ip': '10.0.0.99'}).encode()
        with patch('mqtt_handler.get_connection', side_effect=Exception('db caida')):
            on_message(MagicMock(), None, mock_msg)

    def test_lwt_db_excepcion_no_rompe(self, app):
        from mqtt_handler import on_message
        mock_msg = MagicMock()
        mock_msg.topic = 'esp32/lwt/FFFFFFFFFFFF'
        mock_msg.payload = b''
        with patch('mqtt_handler.get_connection', side_effect=Exception('db caida')):
            on_message(MagicMock(), None, mock_msg)


class TestMqttHandlerOnConnectEco:
    """Cubre el hilo interno eco_delayed() lanzado desde on_connect (lineas 40-42)."""

    def test_on_connect_eco_delayed_publica(self):
        from mqtt_handler import on_connect
        client = MagicMock()
        captured = {}

        class ImmediateThread:
            def __init__(self, target=None, daemon=None):
                captured['target'] = target

            def start(self):
                # Ejecutar el target inmediatamente en lugar de en un hilo real
                captured['target']()

        with patch('mqtt_handler.threading.Thread', ImmediateThread), \
             patch('mqtt_handler.time.sleep'):
            on_connect(client, None, None, 0)

        client.publish.assert_called_with('esp32/imagen/eco', 'Python esta vivo')

    def test_huella_resultado_callback_con_excepcion_no_rompe(self, app, client, admin_token):
        from mqtt_handler import on_message

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Callback Falla', 'rut': '88.888.888-8'})

        callback = MagicMock(side_effect=Exception('sse caida'))
        with patch('mqtt_handler._huella_broadcast_callback', callback):
            mock_msg = MagicMock()
            mock_msg.topic = 'esp32/huella/resultado/1'
            mock_msg.payload = json.dumps({
                'persona_id': '1', 'huella_id': 10, 'status': 'ok'
            }).encode()
            # No debe propagar la excepcion del callback
            on_message(MagicMock(), None, mock_msg)


class TestMqttHandlerWatchdogYPingerExtra:
    """Cubre ramas de error y el loop principal de device_watchdog/device_pinger."""

    def test_device_watchdog_initial_sweep_excepcion(self):
        from mqtt_handler import device_watchdog
        with patch('mqtt_handler.get_connection', side_effect=Exception('db caida')), \
             patch('mqtt_handler.time.sleep', side_effect=[StopIteration()]):
            try:
                device_watchdog()
            except StopIteration:
                pass

    def test_device_watchdog_main_loop_marca_vencidos(self):
        from mqtt_handler import device_watchdog, heartbeat_times, heartbeat_lock
        with heartbeat_lock:
            heartbeat_times['VENCIDOWD01'] = 0

        with patch('mqtt_handler.get_connection') as mock_conn, \
             patch('mqtt_handler.time.sleep', side_effect=[None, StopIteration()]), \
             patch('mqtt_handler.time.time', return_value=999999):
            mock_cur = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cur
            mock_cur.fetchone.return_value = (1, 'DeviceWD', '10.0.0.1', 'inactivo')
            try:
                device_watchdog()
            except StopIteration:
                pass

        with heartbeat_lock:
            heartbeat_times.clear()

    def test_device_watchdog_main_loop_excepcion_db(self):
        from mqtt_handler import device_watchdog, heartbeat_times, heartbeat_lock
        with heartbeat_lock:
            heartbeat_times['VENCIDOWD02'] = 0

        call_count = {'n': 0}

        def get_connection_side_effect():
            call_count['n'] += 1
            if call_count['n'] == 1:
                return MagicMock()
            raise Exception('db caida en loop')

        with patch('mqtt_handler.get_connection', side_effect=get_connection_side_effect), \
             patch('mqtt_handler.time.sleep', side_effect=[None, StopIteration()]), \
             patch('mqtt_handler.time.time', return_value=999999):
            try:
                device_watchdog()
            except StopIteration:
                pass

        with heartbeat_lock:
            heartbeat_times.clear()

    def test_device_pinger_vencido_marca_inactivo_exito(self):
        """Cubre el camino exitoso de marcado de vencidos en device_pinger
        (lineas 295-304): requiere t > 0 para que el filtro de 'vencidos'
        lo considere (a diferencia de device_watchdog, que no exige t > 0)."""
        from mqtt_handler import device_pinger, heartbeat_times, heartbeat_lock
        with heartbeat_lock:
            heartbeat_times['PINGVENC00'] = 1  # timestamp viejo pero > 0

        mock_client = MagicMock()
        call_count = {'n': 0}

        def get_connection_side_effect():
            call_count['n'] += 1
            mock = MagicMock()
            if call_count['n'] == 1:
                mock.cursor.return_value.fetchall.return_value = []
            else:
                mock.cursor.return_value.fetchone.return_value = (1, 'DeviceVencido', '10.0.0.9', 'inactivo')
            return mock

        with patch('mqtt_handler._mqtt_client', mock_client), \
             patch('mqtt_handler.time.sleep', side_effect=[None, StopIteration()]), \
             patch('mqtt_handler.time.time', return_value=999999), \
             patch('mqtt_handler.get_connection', side_effect=get_connection_side_effect):
            try:
                device_pinger()
            except StopIteration:
                pass

        with heartbeat_lock:
            heartbeat_times.clear()

    def test_device_pinger_vencido_excepcion_db(self):
        from mqtt_handler import device_pinger, heartbeat_times, heartbeat_lock
        with heartbeat_lock:
            heartbeat_times['PINGVENC01'] = 1  # timestamp viejo pero > 0

        mock_client = MagicMock()
        call_count = {'n': 0}

        def get_connection_side_effect():
            call_count['n'] += 1
            if call_count['n'] == 1:
                mock = MagicMock()
                mock.cursor.return_value.fetchall.return_value = []
                return mock
            raise Exception('db caida al marcar vencido')

        with patch('mqtt_handler._mqtt_client', mock_client), \
             patch('mqtt_handler.time.sleep', side_effect=[None, StopIteration()]), \
             patch('mqtt_handler.time.time', return_value=999999), \
             patch('mqtt_handler.get_connection', side_effect=get_connection_side_effect):
            try:
                device_pinger()
            except StopIteration:
                pass

        with heartbeat_lock:
            heartbeat_times.clear()

    def test_device_pinger_excepcion_general(self):
        from mqtt_handler import device_pinger
        mock_client = MagicMock()
        with patch('mqtt_handler._mqtt_client', mock_client), \
             patch('mqtt_handler.time.sleep', side_effect=[None, StopIteration()]), \
             patch('mqtt_handler.get_connection', side_effect=Exception('fallo general')):
            try:
                device_pinger()
            except StopIteration:
                pass

    def test_start_mqtt_con_huella_broadcast_callback(self):
        from mqtt_handler import start_mqtt
        with patch('mqtt_handler.SECURE_MODE', False), \
             patch('mqtt_handler.mqtt.Client') as mock_client_class, \
             patch('mqtt_handler.threading.Thread'):
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance
            result = start_mqtt(huella_broadcast_callback=lambda x: None)
            assert result is not None
