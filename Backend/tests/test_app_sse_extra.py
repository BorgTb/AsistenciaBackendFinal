"""Tests para las ramas SSE de app.py no cubiertas por los tests existentes:

- device_stream(): cola llena al reproducir recent_events (queue.Full, lineas
  51-52) y keepalive cuando no llegan eventos a tiempo (queue.Empty, linea 60).
- huella_stream(): keepalive cuando no llegan eventos a tiempo (linea 95).

Las pruebas de app.py existentes (test_app.py/test_app_extra.py) no invocan
estos generadores directamente, asi que estas ramas quedaban sin ejercitar.
"""
import queue as queue_module
from unittest.mock import MagicMock


class _FakeQueueFullOnPut:
    """Cola que siempre levanta queue.Full al intentar encolar (put_nowait)
    y queue.Empty al intentar leer (get), para forzar ambas ramas de error
    sin depender de timing real."""

    def __init__(self, maxsize=0):
        self.maxsize = maxsize

    def put_nowait(self, item):
        raise queue_module.Full

    def get(self, timeout=None):
        raise queue_module.Empty


class _FakeQueueOneItemThenEmpty:
    """Cola que entrega un dato real en la primera lectura y luego Empty,
    para cubrir la rama exitosa de 'yield data: ...' (linea 95 de app.py)."""

    def __init__(self, maxsize=0):
        self.maxsize = maxsize
        self._calls = 0

    def put_nowait(self, item):
        pass

    def get(self, timeout=None):
        self._calls += 1
        if self._calls == 1:
            return {'evento': 'huella_actualizada'}
        raise queue_module.Empty


class TestDeviceStreamSSE:

    def test_device_stream_full_al_reproducir_eventos_y_keepalive(self, app, monkeypatch):
        import app as app_module

        app_module.recent_events.clear()
        app_module.recent_events.append({'evento': 'previo'})

        monkeypatch.setattr(app_module.queue, 'Queue', _FakeQueueFullOnPut)

        with app.test_request_context('/sse/devices'):
            resp = app_module.device_stream()
            gen = resp.response

            # El primer chunk debe ser el keepalive (linea 60), ya que el
            # evento previo no pudo encolarse (Full, lineas 51-52) y la
            # lectura posterior tambien falla con Empty.
            chunk = next(gen)
            assert chunk == ': keepalive\n\n'

            gen.close()  # dispara GeneratorExit -> limpieza de device_clients

    def test_device_stream_generator_exit_limpia_cliente(self, app):
        import app as app_module

        with app.test_request_context('/sse/devices'):
            resp = app_module.device_stream()
            gen = resp.response
            # Forzar GeneratorExit inmediatamente sin consumir ningun chunk
            gen.close()
            # No debe quedar ningun cliente colgado tras el cierre
            assert len(app_module.device_clients) == 0


class TestHuellaStreamSSE:

    def test_huella_stream_yield_dato_real(self, app, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module.queue, 'Queue', _FakeQueueOneItemThenEmpty)

        with app.test_request_context('/sse/huellas'):
            resp = app_module.huella_stream()
            gen = resp.response

            chunk = next(gen)
            assert chunk.startswith('data: ')
            assert 'huella_actualizada' in chunk

            gen.close()

    def test_huella_stream_keepalive(self, app, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module.queue, 'Queue', _FakeQueueFullOnPut)

        with app.test_request_context('/sse/huellas'):
            resp = app_module.huella_stream()
            gen = resp.response

            chunk = next(gen)
            assert chunk == ': keepalive\n\n'

            gen.close()

    def test_huella_stream_generator_exit_limpia_cliente(self, app):
        import app as app_module

        with app.test_request_context('/sse/huellas'):
            resp = app_module.huella_stream()
            gen = resp.response
            gen.close()
            assert len(app_module.huella_clients) == 0


class TestAppMainEntrypoint:
    """Cubre el bloque `if __name__ == '__main__':` (lineas 121-140).

    Este bloque solo se ejecuta al correr `python app.py` directamente, nunca
    al importar el modulo. Se ejecuta aqui con runpy como run_name='__main__'
    para forzar su evaluacion real, con init_db, start_mqtt y Flask.run
    mockeados para no levantar servicios de verdad.
    """

    def test_main_modo_no_seguro(self, monkeypatch):
        import runpy
        import flask

        monkeypatch.setenv('SECURE_MODE', 'false')
        monkeypatch.setattr('database.init_db', MagicMock())
        monkeypatch.setattr('mqtt_handler.start_mqtt', MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(flask.Flask, 'run', MagicMock())

        runpy.run_module('app', run_name='__main__')

        flask.Flask.run.assert_called_once()
        _, kwargs = flask.Flask.run.call_args
        assert kwargs.get('port') == 5000

    def test_main_modo_seguro(self, monkeypatch):
        import runpy
        import flask

        monkeypatch.setenv('SECURE_MODE', 'true')
        monkeypatch.setattr('database.init_db', MagicMock())
        monkeypatch.setattr('mqtt_handler.start_mqtt', MagicMock(return_value=MagicMock()))
        monkeypatch.setattr(flask.Flask, 'run', MagicMock())

        runpy.run_module('app', run_name='__main__')

        # En modo seguro se invoca app.run() para HTTP en el hilo principal;
        # el hilo HTTPS esta mockeado (fixture autouse mock_thread), por lo
        # que su target (la lambda con el segundo app.run) no se ejecuta solo.
        assert flask.Flask.run.called
        calls_ports = [c.kwargs.get('port') for c in flask.Flask.run.call_args_list]
        assert 5000 in calls_ports
