class TestDuplicadosPersonas:
    """Tests para GET /api/personas/duplicados y POST /api/personas/merge"""

    def test_duplicados_sin_auth(self, client):
        resp = client.get('/api/personas/duplicados')
        assert resp.status_code == 401

    def test_duplicados_vacio(self, client, admin_token):
        resp = client.get('/api/personas/duplicados',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_merge_faltan_campos(self, client, admin_token):
        resp = client.post('/api/personas/merge',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 400

    def test_merge_persona_no_encontrada(self, client, admin_token):
        resp = client.post('/api/personas/merge',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'mantener_id': 999, 'eliminar_id': 998})
        assert resp.status_code == 404

    def test_merge_exitoso(self, client, admin_token):
        c1 = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Mantener', 'rut': '50.111.111-1'})
        id1 = c1.get_json()['id']
        c2 = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Eliminar', 'rut': '50.111.111-2'})
        id2 = c2.get_json()['id']

        resp = client.post('/api/personas/merge',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'mantener_id': id1, 'eliminar_id': id2})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_merge_sin_auth(self, client):
        resp = client.post('/api/personas/merge',
            json={'mantener_id': 1, 'eliminar_id': 2})
        # token_opcional no bloquea, pero personas no existen → 404
        assert resp.status_code == 404

    def test_merge_duplicado_twice_fails(self, client, admin_token):
        c1 = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'M2', 'rut': '51.111.111-1'})
        id1 = c1.get_json()['id']
        c2 = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'E2', 'rut': '51.111.111-2'})
        id2 = c2.get_json()['id']

        client.post('/api/personas/merge',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'mantener_id': id1, 'eliminar_id': id2})
        resp = client.post('/api/personas/merge',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'mantener_id': id1, 'eliminar_id': id2})
        assert resp.status_code == 404


class TestPersonaBiometrico:
    """Tests para GET /api/personas/<id>/biometrico"""

    def test_biometrico_not_found(self, client, admin_token):
        resp = client.get('/api/personas/99999/biometrico',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_biometrico_exitoso(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Bio', 'rut': '60.111.111-1'})
        resp = client.get('/api/personas/1/biometrico',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['persona_id'] == '1'
        assert 'huella_id' in data
        assert 'total_encodings' in data
        assert 'tiene_consentimiento' in data
        assert 'tiene_preview' in data

    def test_biometrico_sin_auth(self, client):
        resp = client.get('/api/personas/1/biometrico')
        # token_opcional no bloquea, pero persona no existe → 404
        assert resp.status_code == 404

    def test_biometrico_empleador_otra_empresa(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'BioAdm', 'rut': '60.111.111-2'})
        resp = client.get('/api/personas/1/biometrico',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 404
