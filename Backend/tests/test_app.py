class TestApp:
    """Tests para el entry point Flask."""

    def test_health_endpoint(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'
        assert data['version'] == '1.0'

    def test_health_no_cache(self, client):
        resp = client.get('/health', headers={'Cache-Control': 'no-cache'})
        assert resp.status_code == 200

    def test_all_blueprints_registered(self, app):
        blueprints = {bp.name for bp in app.iter_blueprints()}
        expected = {
            'auth', 'personas', 'turnos', 'asignaciones',
            'asistencias', 'facial', 'dispositivos', 'logs', 'erp'
        }
        missing = expected - blueprints
        assert not missing, f"Blueprints missing: {missing}"

    def test_cors_headers_present(self, client):
        resp = client.get('/health', headers={'Origin': 'http://localhost:3000'})
        assert resp.status_code == 200
        assert 'Access-Control-Allow-Origin' in resp.headers

    def test_404_on_unknown_route(self, client):
        resp = client.get('/api/nonexistent')
        assert resp.status_code == 404

    def test_method_not_allowed(self, client):
        resp = client.put('/health')
        assert resp.status_code == 405

    def test_sse_huella_endpoint_exists(self, app):
        resp = app.test_client().get('/sse/huellas')
        assert resp.status_code == 200
        assert resp.mimetype == 'text/event-stream'
        resp.close()

    def test_broadcast_huella_update_adds_to_clients(self, app):
        from app import broadcast_huella_update, huella_clients, huella_clients_lock
        import queue
        q = queue.Queue()
        with huella_clients_lock:
            huella_clients.append(q)
        broadcast_huella_update({'status': 'ok', 'huella_id': 1})
        data = q.get(timeout=1)
        assert data['status'] == 'ok'
        with huella_clients_lock:
            huella_clients.remove(q)

    def test_broadcast_device_update_adds_to_clients(self, app):
        from app import broadcast_device_update, device_clients, clients_lock
        import queue
        q = queue.Queue()
        with clients_lock:
            device_clients.append(q)
        broadcast_device_update({'status': 'ok', 'device_id': 1})
        data = q.get(timeout=1)
        assert data['status'] == 'ok'
        with clients_lock:
            device_clients.remove(q)

    def test_broadcast_device_update_queue_full_ignored(self, app):
        from app import broadcast_device_update, device_clients, clients_lock
        import queue
        q = queue.Queue(maxsize=1)
        q.put_nowait({'placeholder': True})
        with clients_lock:
            device_clients.append(q)
        broadcast_device_update({'status': 'ignored'})
        with clients_lock:
            device_clients.remove(q)

    def test_broadcast_huella_update_queue_full_ignored(self, app):
        from app import broadcast_huella_update, huella_clients, huella_clients_lock
        import queue
        q = queue.Queue(maxsize=1)
        q.put_nowait({'placeholder': True})
        with huella_clients_lock:
            huella_clients.append(q)
        broadcast_huella_update({'status': 'ignored'})
        with huella_clients_lock:
            huella_clients.remove(q)
