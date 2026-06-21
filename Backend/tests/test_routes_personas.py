class TestRoutesPersonas:
    """Tests para /api/personas — CRUD, huella, consentimiento, olvido."""

    def test_listar_personas_vacio(self, client):
        resp = client.get('/api/personas')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_crear_persona_admin(self, client, admin_token):
        resp = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Juan Perez', 'rut': '11.222.333-4', 'email': 'juan@test.cl'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['id'] is not None

    def test_crear_sin_token_default_empresa(self, client):
        resp = client.post('/api/personas', json={
            'nombre': 'Sin Token', 'rut': '99.888.777-6'
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_crear_persona_sin_nombre(self, client, admin_token):
        resp = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'rut': '11.111.111-1'})
        assert resp.status_code == 400

    def test_crear_persona_sin_rut(self, client, admin_token):
        resp = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Sin RUT'})
        assert resp.status_code == 400

    def test_listar_personas_admin(self, client, admin_token):
        for i in range(3):
            client.post('/api/personas',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'nombre': f'P{i}', 'rut': f'10.000.00{i}-{i}'})
        resp = client.get('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert len(resp.get_json()) == 3

    def test_estructura_persona(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '55.555.555-5'})
        resp = client.get('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'})
        p = resp.get_json()[0]
        assert 'id' in p
        assert 'nombre' in p
        assert 'rut' in p
        assert 'email' in p
        assert 'huella_id' in p
        assert 'empresa_id' in p
        assert 'fecha_registro' in p
        assert 'sincronizado' in p

    def test_update_persona_nombre(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Original', 'rut': '44.444.444-4'})
        resp = client.put('/api/personas/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Modificado'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        assert resp.get_json()['persona']['nombre'] == 'Modificado'

    def test_update_email_invalido(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '66.666.666-6'})
        resp = client.put('/api/personas/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'email': 'no-arroba'})
        assert resp.status_code == 400

    def test_rut_no_editable(self, client, admin_token):
        resp = client.put('/api/personas/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'rut': '00.000.000-0'})
        assert resp.status_code == 400

    def test_delete_persona_admin_hard(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '77.777.777-7'})
        resp = client.delete('/api/personas/1',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        personas = client.get('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert len(personas.get_json()) == 0

    def test_delete_persona_empleador_soft(self, client, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Emp', 'rut': '88.888.888-8'})
        resp = client.delete('/api/personas/1',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200

    def test_set_huella_id(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '12.345.678-9'})
        resp = client.put('/api/personas/1/huella',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'huella_id': 5})
        assert resp.status_code == 200
        assert resp.get_json()['persona']['huella_id'] == 5

    def test_huella_id_fuera_rango(self, client, admin_token):
        resp = client.put('/api/personas/1/huella',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'huella_id': 200})
        assert resp.status_code == 400

    def test_huella_id_invalido(self, client, admin_token):
        resp = client.put('/api/personas/1/huella',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'huella_id': 'abc'})
        assert resp.status_code == 400

    def test_huella_id_duplicada(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P1', 'rut': '10.000.000-1'})
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P2', 'rut': '10.000.000-2'})
        client.put('/api/personas/1/huella',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'huella_id': 3})
        resp = client.put('/api/personas/2/huella',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'huella_id': 3})
        assert resp.status_code == 409

    def test_registrar_consentimiento(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '11.000.000-1'})
        resp = client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'version_politica': '1.0', 'metodo_aceptacion': 'web'})
        assert resp.status_code == 200

    def test_eliminar_datos_biometricos(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Bio', 'rut': '12.000.000-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.delete('/api/personas/1/datos-biometricos',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert 'eliminados' in resp.get_json().get('mensaje', '').lower()

    def test_aislamiento_multi_tenant_empleador(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'AdminP', 'rut': '20.000.000-1'})
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'EmpP', 'rut': '20.000.000-2'})
        resp = client.get('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'})
        personas = resp.get_json()
        nombres = [p['nombre'] for p in personas]
        assert 'EmpP' in nombres
        assert 'AdminP' not in nombres

    def test_update_persona_not_found(self, client, admin_token):
        resp = client.put('/api/personas/99999',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'No existe'})
        assert resp.status_code == 404

    def test_delete_persona_not_found(self, client, admin_token):
        resp = client.delete('/api/personas/99999',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_consentimiento_sin_auth(self, client):
        resp = client.post('/api/personas/1/consentimiento', json={})
        assert resp.status_code in (401, 403)

    def test_consentimiento_persona_not_found(self, client, admin_token):
        resp = client.post('/api/personas/99999/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 404

    def test_huella_persona_not_found(self, client, admin_token):
        resp = client.put('/api/personas/99999/huella',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'huella_id': 5})
        assert resp.status_code == 404

    def test_eliminar_biometricos_not_found(self, client, admin_token):
        resp = client.delete('/api/personas/99999/datos-biometricos',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 404

    def test_eliminar_biometricos_sin_auth(self, client):
        resp = client.delete('/api/personas/1/datos-biometricos')
        assert resp.status_code in (401, 403)

    def test_update_persona_email_invalido(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Update Me', 'rut': '44.444.444-4'})
        resp = client.put('/api/personas/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'email': 'not-an-email'})
        assert resp.status_code == 400

    def test_update_persona_not_found(self, client, admin_token):
        resp = client.put('/api/personas/99999',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Ghost'})
        assert resp.status_code == 404

    def test_delete_persona_db_error(self, client, admin_token):
        from unittest.mock import patch, MagicMock
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'ToDelete', 'rut': '55.555.555-5'})
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.delete('/api/personas/3',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500
