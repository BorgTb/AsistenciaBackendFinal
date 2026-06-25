import json
import queue
from unittest.mock import patch


class TestAppExtra:

    def test_broadcast_device_update_queue_full(self, app):
        from app import broadcast_device_update, device_clients, clients_lock
        q = queue.Queue(maxsize=1)
        q.put_nowait({'existing': True})
        with clients_lock:
            device_clients.append(q)
        broadcast_device_update({'new': True})
        with clients_lock:
            device_clients.remove(q)

    def test_broadcast_huella_update_queue_full(self, app):
        from app import broadcast_huella_update, huella_clients, huella_clients_lock
        q = queue.Queue(maxsize=1)
        q.put_nowait({'existing': True})
        with huella_clients_lock:
            huella_clients.append(q)
        broadcast_huella_update({'new': True})
        with huella_clients_lock:
            huella_clients.remove(q)

    def test_device_stream_endpoint_exists(self, client):
        from app import broadcast_device_update
        broadcast_device_update({'test': 'replay'})
        resp = client.get('/sse/devices')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/event-stream'
        resp.close()

    def test_huella_stream_endpoint_exists(self, client):
        resp = client.get('/sse/huellas')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/event-stream'
        resp.close()

    def test_broadcast_device_adds_to_recent_events(self, app):
        from app import broadcast_device_update, recent_events
        recent_events.clear()
        broadcast_device_update({'event': 'test'})
        assert len(recent_events) >= 1
        assert recent_events[-1] == {'event': 'test'}
