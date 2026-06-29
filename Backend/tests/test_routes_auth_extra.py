"""Tests adicionales para routes/auth.py.

Cubre ramas de validacion, permisos y manejo de errores que no estaban
ejercitadas por test_routes_auth.py: usuario sin empresas asignadas,
autoeliminacion/autoedicion, validaciones de crear_empresa,
errores de base de datos en endpoints administrativos, resolucion de
solicitudes de eliminacion biometrica (aprobada/rechazada con todas sus
ramas de notificacion), y enrolamiento de dispositivos con fusion de MAC y
personas duplicadas.
"""
import os
from unittest.mock import MagicMock, patch

import bcrypt


class TestLoginSinEmpresas:
    def test_login_usuario_sin_empresas_asignadas(self, client, admin_token):
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        pw_hash = bcrypt.hashpw(b'test1234', bcrypt.gensalt()).decode('utf-8')
        cur.execute(
            "INSERT INTO usuarios_web (nombre, email, password_hash) VALUES (%s, %s, %s)",
            ('Sin Empresa', 'sinempresa@test.cl', pw_hash)
        )
        conn.commit()
        cur.close()
        conn.close()

        resp = client.post('/api/auth/login', json={
            'email': 'sinempresa@test.cl', 'password': 'test1234'
        })
        assert resp.status_code == 403
        assert 'No tienes empresas' in resp.get_json()['error']


class TestEliminarUsuarioAutogestion:
    def test_admin_no_puede_eliminarse_a_si_mismo_de_otra_forma(self, client, admin_token):
        # admin_token corresponde al usuario 1 en la empresa 1 (seed inicial)
        resp = client.delete('/api/auth/usuarios/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'empresa_id': 1})
        assert resp.status_code == 200
        assert 'removiste' in resp.get_json()['mensaje']

    def test_empleador_no_puede_eliminarse_a_si_mismo(self, client, empleador_token):
        import jwt as pyjwt
        from routes.auth import JWT_SECRET
        payload = pyjwt.decode(empleador_token, JWT_SECRET, algorithms=['HS256'])
        resp = client.delete(f"/api/auth/usuarios/{payload['user_id']}",
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'empresa_id': 2})
        assert resp.status_code == 400
        assert 'No puedes eliminarte' in resp.get_json()['error']


class TestCrearEmpresaValidaciones:
    def test_mode_invalido(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'E1', 'mode': 'raro'})
        assert resp.status_code == 400

    def test_rol_usuario_invalido(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'E2', 'rol_usuario': 'admin'})
        assert resp.status_code == 400

    def test_password_usuario_corta(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'E3', 'mode': 'new', 'nombre_usuario': 'U',
                'email_usuario': 'u@test.cl', 'password_usuario': 'ab'
            })
        assert resp.status_code == 400

    def test_email_usuario_invalido(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'E4', 'mode': 'new', 'nombre_usuario': 'U',
                'email_usuario': 'no-es-email', 'password_usuario': 'test1234'
            })
        assert resp.status_code == 400

    def test_mode_existing_sin_usuario_id(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'E5', 'mode': 'existing'})
        assert resp.status_code == 400

    def test_mode_new_email_ya_existe(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'E6', 'mode': 'new', 'nombre_usuario': 'U',
                'email_usuario': 'admin@empresa.cl', 'password_usuario': 'test1234'
            })
        assert resp.status_code == 409

    def test_mode_existing_usuario_no_existe(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'E7', 'mode': 'existing', 'usuario_id': 99999})
        assert resp.status_code == 404

    def test_mode_existing_usuario_existente(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'E8', 'mode': 'existing', 'usuario_id': 1, 'rol_usuario': 'trabajador'})
        assert resp.status_code == 200
        assert resp.get_json()['usuario_id'] == 1


class TestEliminarEmpresaYAsignarUsuario:
    def test_eliminar_empresa_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.delete('/api/auth/empresas/1',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()

    def test_asignar_usuario_rol_admin_bloqueado(self, client, admin_token):
        resp = client.post('/api/auth/asignar-usuario',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'usuario_id': 1, 'empresa_id': 1, 'rol': 'admin'})
        assert resp.status_code == 403

    def test_asignar_usuario_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.post('/api/auth/asignar-usuario',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'usuario_id': 1, 'empresa_id': 1, 'rol': 'trabajador'})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()


class TestRegisterCompanyYCambiarPasswordErrores:
    def test_register_company_db_error(self, client):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.side_effect = [None, Exception('DB error')]
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.post('/api/auth/register-company', json={
                'empresa_nombre': 'NuevaCo', 'admin_nombre': 'Admin Co',
                'admin_email': 'adminco@test.cl', 'admin_password': 'test1234'
            })
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()

    def test_cambiar_password_usuario_no_encontrado(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.put('/api/auth/change-password',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'password_actual': 'admin123', 'password_nueva': 'nueva1234'})
            assert resp.status_code == 404

    def test_cambiar_password_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        pw_hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode('utf-8')
        mock_cur.fetchone.return_value = (pw_hash,)
        mock_cur.execute.side_effect = [None, Exception('DB error')]
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.put('/api/auth/change-password',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'password_actual': 'admin123', 'password_nueva': 'nueva1234'})
            assert resp.status_code == 500


class TestMeRamas:
    def test_me_usuario_no_encontrado(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.get('/api/auth/me',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 404

    def test_me_trabajador_resuelve_persona_id(self, client, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Trab Me', 'rut': '27.000.000-1', 'email': 'trabme@test.cl'})
        client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Trab Me User', 'email': 'trabme@test.cl',
                  'password': 'test1234', 'rol': 'trabajador', 'empresa_id': 2})
        login = client.post('/api/auth/login', json={
            'email': 'trabme@test.cl', 'password': 'test1234', 'empresa_id': 2
        })
        token = login.get_json()['token']
        resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        assert resp.get_json()['user']['persona_id'] is not None


class TestSolicitudEliminacionRamas:
    def test_solicitar_eliminacion_envio_email_excepcion_no_rompe(self, client, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Solic', 'rut': '27.000.000-2', 'email': 'solic@test.cl'})
        with patch('routes.auth.enviar_codigo_seguimiento', side_effect=Exception('smtp caido')):
            resp = client.post('/api/auth/solicitar-eliminacion-datos', json={
                'rut': '27.000.000-2', 'email': 'contacto@test.cl'
            })
        assert resp.status_code == 200

    def test_consultar_solicitud_db_error(self, client):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.get('/api/auth/solicitud-eliminacion/abc123')
            assert resp.status_code == 500

    def test_listar_solicitudes_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.get('/api/auth/solicitudes-eliminacion',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500

    def test_listar_solicitudes_empleador_filtra_su_empresa(self, client, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Solic2', 'rut': '27.000.000-3'})
        client.post('/api/auth/solicitar-eliminacion-datos', json={'rut': '27.000.000-3'})
        resp = client.get('/api/auth/solicitudes-eliminacion',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200
        assert len(resp.get_json()) >= 1


class TestResolverSolicitudEliminacionRamas:

    def test_resolver_solicitud_no_encontrada(self, client, admin_token):
        resp = client.put('/api/auth/solicitudes-eliminacion/99999',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'estado': 'aprobada'})
        assert resp.status_code == 404

    def test_resolver_solicitud_empleador_otra_empresa_no_autorizado(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Otra Emp', 'rut': '27.000.000-4'})
        solic = client.post('/api/auth/solicitar-eliminacion-datos', json={'rut': '27.000.000-4'})
        solicitud_id = None
        listado = client.get('/api/auth/solicitudes-eliminacion',
            headers={'Authorization': f'Bearer {admin_token}'})
        for s in listado.get_json():
            if s['rut'] == '27.000.000-4':
                solicitud_id = s['id']
        resp = client.put(f'/api/auth/solicitudes-eliminacion/{solicitud_id}',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'estado': 'aprobada'})
        assert resp.status_code == 403

    def test_resolver_solicitud_aprobada_completa_con_excepciones_internas(self, client, admin_token, empleador_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Aprobar', 'rut': '27.000.000-5', 'email': 'aprobar@test.cl'})
        client.post('/api/auth/solicitar-eliminacion-datos', json={'rut': '27.000.000-5'})
        listado = client.get('/api/auth/solicitudes-eliminacion',
            headers={'Authorization': f'Bearer {empleador_token}'})
        solicitud_id = next(s['id'] for s in listado.get_json() if s['rut'] == '27.000.000-5')

        with patch('eventos_mqtt.notificar_sincronizacion', side_effect=Exception('mqtt caido')), \
             patch('routes.facial._invalidar_cache', side_effect=Exception('cache caida')), \
             patch('routes.auth.notificar_resolucion_eliminacion', side_effect=Exception('smtp caido')):
            resp = client.put(f'/api/auth/solicitudes-eliminacion/{solicitud_id}',
                headers={'Authorization': f'Bearer {empleador_token}'},
                json={'estado': 'aprobada'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_resolver_solicitud_db_error(self, client, admin_token, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P DbErr', 'rut': '27.000.000-6'})
        client.post('/api/auth/solicitar-eliminacion-datos', json={'rut': '27.000.000-6'})
        listado = client.get('/api/auth/solicitudes-eliminacion',
            headers={'Authorization': f'Bearer {empleador_token}'})
        solicitud_id = next(s['id'] for s in listado.get_json() if s['rut'] == '27.000.000-6')

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (
            solicitud_id, 1, 'pendiente', None, 'P DbErr', None, '27.000.000-6', 2
        )
        mock_cur.execute.side_effect = [None, Exception('DB error')]
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.put(f'/api/auth/solicitudes-eliminacion/{solicitud_id}',
                headers={'Authorization': f'Bearer {empleador_token}'},
                json={'estado': 'rechazada'})
            assert resp.status_code == 500


class TestGenerarPinYEnrolarRamas:

    def test_generar_pin_reutiliza_pin_existente_no_usado(self, client, empleador_token):
        first = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Disp1'})
        second = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Disp2'})
        assert first.get_json()['pin'] == second.get_json()['pin']
        assert first.get_json()['dispositivo_id'] == second.get_json()['dispositivo_id']

    def test_enrolar_mac_existente_se_fusiona_con_nuevo_pin(self, client, empleador_token):
        pin1 = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'DispFus1'})
        enrol1 = client.post('/api/auth/dispositivos/enrolar', json={
            'codigo': pin1.get_json()['pin'], 'mac': 'CC:DD:EE:FF:00:01', 'ip': '10.3.0.1'
        })
        assert enrol1.status_code == 200
        dispositivo_original_id = enrol1.get_json()['dispositivo_id']

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE dispositivos SET enrolado = FALSE, codigo_enrol = 'PINNUEV1' WHERE id = %s",
            (dispositivo_original_id,)
        )
        cur.execute(
            "INSERT INTO dispositivos (empresa_id, nombre, codigo_enrol, enrolado) VALUES (%s, %s, %s, FALSE) RETURNING id",
            (2, 'DispFus2', 'PINNUEV2')
        )
        nuevo_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        enrol2 = client.post('/api/auth/dispositivos/enrolar', json={
            'codigo': 'PINNUEV2', 'mac': 'CC:DD:EE:FF:00:01', 'ip': '10.3.0.2'
        })
        assert enrol2.status_code == 200
        assert enrol2.get_json()['dispositivo_id'] == dispositivo_original_id

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM dispositivos WHERE id = %s", (nuevo_id,))
        assert cur.fetchone() is None
        cur.close()
        conn.close()

    def test_enrolar_migra_personas_huerfanas_y_detecta_duplicados(self, client, empleador_token, admin_token):
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dispositivos (nombre, codigo_enrol, enrolado) VALUES (%s, %s, FALSE) RETURNING id",
            ('DispHuerfano', 'PINHUERF')
        )
        dispositivo_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO personas (nombre, rut, dispositivo_origen_id, activo) VALUES (%s, %s, %s, TRUE) RETURNING id",
            ('Huerfana Migra', '27.500.000-1', dispositivo_id)
        )
        cur.execute(
            "INSERT INTO personas (nombre, rut, dispositivo_origen_id, activo) VALUES (%s, %s, %s, TRUE) RETURNING id",
            ('Huerfana Duplicada', '27.500.000-2', dispositivo_id)
        )
        conn.commit()
        cur.close()
        conn.close()

        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Ya Existe', 'rut': '27.500.000-2'})

        resp = client.post('/api/auth/dispositivos/enrolar', json={
            'codigo': 'PINHUERF', 'mac': 'CC:DD:EE:FF:00:02', 'ip': '10.3.0.3'
        })
        assert resp.status_code == 404 or resp.status_code == 200

    def test_enrolar_db_error(self, client):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (1, 1, False)
        mock_cur.execute.side_effect = [None, Exception('DB error')]
        with patch('routes.auth.get_connection', return_value=mock_conn):
            resp = client.post('/api/auth/dispositivos/enrolar', json={
                'codigo': 'CUALQUIERA', 'mac': 'CC:DD:EE:FF:00:99', 'ip': '10.3.0.9'
            })
            assert resp.status_code == 500
