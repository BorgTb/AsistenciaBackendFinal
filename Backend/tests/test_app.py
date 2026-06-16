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
