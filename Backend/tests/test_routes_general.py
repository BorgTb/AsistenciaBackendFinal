class TestRoutesLogs:
    """Tests para /api/logs — logs de sincronizacion."""

    def test_get_logs_requires_auth(self, client):
        resp = client.get('/api/logs')
        assert resp.status_code == 401

    def test_get_logs_admin(self, client, admin_token):
        resp = client.get('/api/logs',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_get_logs_empleador(self, client, empleador_token):
        resp = client.get('/api/logs',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_logs_trabajador_rechazado(self, client, trabajador_token):
        resp = client.get('/api/logs',
            headers={'Authorization': f'Bearer {trabajador_token}'})
        assert resp.status_code == 403

    def test_clear_logs_admin(self, client, admin_token):
        resp = client.delete('/api/logs',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_clear_logs_empleador(self, client, empleador_token):
        resp = client.delete('/api/logs',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_clear_logs_sin_token(self, client):
        resp = client.delete('/api/logs')
        assert resp.status_code == 401

    def test_logs_lista_vacia_funciona(self, client, admin_token):
        resp = client.get('/api/logs',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_logs_empleador_solo_su_empresa(self, client, admin_token, empleador_token):
        resp_admin = client.get('/api/logs',
            headers={'Authorization': f'Bearer {admin_token}'})
        admin_count = len(resp_admin.get_json())
        resp_emp = client.get('/api/logs',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp_emp.status_code == 200
        assert len(resp_emp.get_json()) <= admin_count


class TestRoutesTurnos:
    """Tests para /api/turnos — CRUD de turnos."""

    def test_listar_turnos_vacio(self, client):
        resp = client.get('/api/turnos')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_crear_turno_con_admin_token(self, client, admin_token):
        resp = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Turno diurno', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L,M,X,J,V'}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['id'] is not None

    def test_crear_turno_con_token_empleador(self, client, empleador_token):
        resp = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Turno noche', 'inicio': '18:00', 'fin': '02:00', 'dias': 'L,M'}
        )
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_listar_turnos_despues_de_crear(self, client, admin_token):
        client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Turno A', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L,M'})
        client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Turno B', 'inicio': '14:00', 'fin': '22:00', 'dias': 'X,J,V'})
        resp = client.get('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        turnos = resp.get_json()
        assert len(turnos) >= 2
        nombres = [t['nombre'] for t in turnos]
        assert 'Turno A' in nombres
        assert 'Turno B' in nombres

    def test_delete_turno_admin(self, client, admin_token):
        create = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Turno X', 'inicio': '10:00', 'fin': '19:00', 'dias': 'S,D'})
        turno_id = create.get_json()['id']
        resp = client.delete(f'/api/turnos/{turno_id}',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_delete_turno_inexistente(self, client, admin_token):
        resp = client.delete('/api/turnos/99999',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_turnos_estructura_respuesta(self, client, admin_token):
        client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T1', 'inicio': '08:00', 'fin': '18:00', 'dias': 'L'})
        resp = client.get('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'})
        t = resp.get_json()[0]
        assert 'id' in t
        assert 'nombre' in t
        assert 'inicio' in t
        assert 'fin' in t
        assert 'dias' in t
        assert 'empresa_id' in t

    def test_empleador_solo_ve_turnos_propia_empresa(self, client, admin_token, empleador_token):
        client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Turno Admin', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        resp = client.get('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'})
        turnos = resp.get_json()
        for t in turnos:
            assert t['empresa_id'] == 2 or t['nombre'] != 'Turno Admin'

    def test_trabajador_ve_turnos_asignados(self, client, admin_token, empleador_token, trabajador_token):
        create = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Turno Trab', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        turno_id = create.get_json()['id']
        client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'persona_id': '1', 'turno_id': str(turno_id)})
        resp = client.get('/api/turnos',
            headers={'Authorization': f'Bearer {trabajador_token}'})
        turnos = resp.get_json()
        assert len(turnos) == 1
        assert turnos[0]['id'] == turno_id

    def test_delete_turno_empleador(self, client, empleador_token):
        c = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'A Borrar', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        resp = client.delete(f"/api/turnos/{c.get_json()['id']}",
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200

    def test_crear_turno_db_error(self, client, admin_token):
        """Fuerza excepcion en DB para cubrir el except block de create_turno."""
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error simulado')
        with patch('routes.turnos.get_connection', return_value=mock_conn):
            resp = client.post('/api/turnos',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'nombre': 'T', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()

    def test_delete_turno_db_error(self, client, admin_token):
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.turnos.get_connection', return_value=mock_conn):
            resp = client.delete('/api/turnos/1',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500

    def test_turnos_filtrados_por_persona_trabajador(self, client, empleador_token):
        """Cubre el JOIN de turnos por persona_id (rol trabajador)."""
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Vinc Trab', 'rut': '55.555.555-5', 'email': 'vinc@t.cl'})
        reg = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Vinc User', 'email': 'vinc@t.cl',
                  'password': 'test1234', 'rol': 'trabajador', 'empresa_id': 2})
        assert reg.status_code == 200, reg.get_data(as_text=True)
        login_resp = client.post('/api/auth/login', json={
            'email': 'vinc@t.cl', 'password': 'test1234', 'empresa_id': 2
        })
        assert login_resp.status_code == 200, login_resp.get_data(as_text=True)
        vinc_data = login_resp.get_json()
        assert vinc_data['user']['persona_id'] is not None, 'persona_id no vinculado'

        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Turno Vinc', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'persona_id': str(vinc_data['user']['persona_id']),
                  'turno_id': str(t.get_json()['id'])})

        vinc_token = vinc_data['token']
        resp = client.get('/api/turnos',
            headers={'Authorization': f'Bearer {vinc_token}'})
        assert resp.status_code == 200
        turnos = resp.get_json()
        assert len(turnos) == 1
        assert turnos[0]['nombre'] == 'Turno Vinc'


class TestRoutesAsignaciones:
    """Tests para /api/asignaciones — CRUD de asignaciones persona-turno."""

    def test_listar_asignaciones_vacio(self, client):
        resp = client.get('/api/asignaciones')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_crear_asignacion_admin(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Persona', 'rut': '10.111.111-1'})
        client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Turno', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        resp = client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': '1', 'turno_id': '1'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_listar_asignaciones_con_datos(self, client, admin_token):
        t_resp = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T', 'inicio': '08:00', 'fin': '18:00', 'dias': 'L'})
        turno_id = str(t_resp.get_json()['id'])
        for i, rut in enumerate(['11.111.111-1', '12.222.222-2', '13.333.333-3'], 1):
            client.post('/api/personas',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'nombre': f'P{i}', 'rut': rut})
            client.post('/api/asignaciones',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'persona_id': str(i), 'turno_id': turno_id})
        resp = client.get('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'})
        asignaciones = resp.get_json()
        assert len(asignaciones) == 3

    def test_eliminar_asignacion_admin(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P', 'rut': '20.000.000-0'})
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T', 'inicio': '08:00', 'fin': '18:00', 'dias': 'L'})
        a = client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': '1', 'turno_id': str(t.get_json()['id'])})
        resp = client.delete(f"/api/asignaciones/{a.get_json()['id']}",
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_estructura_asignacion(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Pepe', 'rut': '30.000.000-1'})
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T1', 'inicio': '08:00', 'fin': '18:00', 'dias': 'L'})
        client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': '1', 'turno_id': str(t.get_json()['id'])})
        resp = client.get('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'})
        a = resp.get_json()[0]
        assert 'id' in a
        assert 'persona_id' in a
        assert 'persona_nombre' in a
        assert 'turno_id' in a
        assert 'turno_nombre' in a
        assert 'fecha_asignacion' in a
        assert 'vigente' in a

    def test_empleador_no_puede_asignar_persona_ajena(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Admin Persona', 'rut': '40.000.000-0'})
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'T2', 'inicio': '08:00', 'fin': '18:00', 'dias': 'L'})
        resp = client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'persona_id': '1', 'turno_id': str(t.get_json()['id'])})
        assert resp.status_code == 403

    def test_delete_asignacion_empleador(self, client, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Emp', 'rut': '50.000.000-1'})
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'T3', 'inicio': '08:00', 'fin': '18:00', 'dias': 'L'})
        a = client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'persona_id': '1', 'turno_id': str(t.get_json()['id'])})
        resp = client.delete(f"/api/asignaciones/{a.get_json()['id']}",
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200

    def test_listar_asignaciones_trabajador(self, client, empleador_token, trabajador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Trab P', 'rut': '60.000.000-1'})
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'T4', 'inicio': '08:00', 'fin': '18:00', 'dias': 'L'})
        client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'persona_id': '2', 'turno_id': str(t.get_json()['id'])})
        resp = client.get('/api/asignaciones',
            headers={'Authorization': f'Bearer {trabajador_token}'})
        asignaciones = resp.get_json()
        assert len(asignaciones) >= 1

    def test_crear_asignacion_por_rut(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'RUT Persona', 'rut': '77.777.777-7'})
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-RUT', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        resp = client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'rut': '77.777.777-7', 'turno_id': str(t.get_json()['id'])})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'id' in data

    def test_crear_asignacion_por_rut_no_existente(self, client, admin_token):
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-RUT2', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        resp = client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'rut': '88.888.888-8', 'turno_id': str(t.get_json()['id'])})
        assert resp.status_code == 404

    def test_crear_asignacion_db_error(self, client, admin_token):
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.asignaciones.get_connection', return_value=mock_conn):
            resp = client.post('/api/asignaciones',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'persona_id': '1', 'turno_id': '1'})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()

    def test_delete_asignacion_db_error(self, client, admin_token):
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.asignaciones.get_connection', return_value=mock_conn):
            resp = client.delete('/api/asignaciones/1',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500


class TestRoutesTurnosNuevos:
    """Tests para PUT turno + campos colacion."""

    def test_crear_turno_con_colacion(self, client, admin_token):
        resp = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'T-Colacion', 'inicio': '08:00', 'fin': '17:00',
                'dias': 'L,M,X', 'con_colacion': True,
                'colacion_inicio': '13:00', 'colacion_fin': '14:00'
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_listar_turnos_incluye_colacion(self, client, admin_token):
        client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-List', 'inicio': '08:00', 'fin': '17:00',
                  'dias': 'L', 'con_colacion': True,
                  'colacion_inicio': '12:00', 'colacion_fin': '13:00'})
        resp = client.get('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        turno = next(t for t in data if t['nombre'] == 'T-List')
        assert turno['con_colacion'] is True

    def test_actualizar_turno(self, client, admin_token):
        create = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-Orig', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        tid = create.get_json()['id']
        resp = client.put(f'/api/turnos/{tid}',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-Updated'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_actualizar_turno_db_error(self, client, admin_token):
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB put error')
        with patch('routes.turnos.get_connection', return_value=mock_conn):
            resp = client.put('/api/turnos/1',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'nombre': 'T-Fail'})
            assert resp.status_code == 500

    def test_crear_turno_sin_auth(self, client):
        resp = client.post('/api/turnos', json={
            'nombre': 'NoAuth', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'
        })
        assert resp.status_code == 401
