class TestRoutesAuth:
    """Tests para /api/auth — login, JWT, roles, registro, enrolamiento."""

    # ── Login ────────────────────────────────────────────
    def test_login_exitoso_admin(self, client):
        resp = client.post('/api/auth/login', json={
            'email': 'admin@empresa.cl', 'password': 'admin123'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'token' in data
        assert 'user' in data
        assert data['user']['rol'] == 'admin'
        assert data['user']['email'] == 'admin@empresa.cl'

    def test_login_password_incorrecta(self, client):
        resp = client.post('/api/auth/login', json={
            'email': 'admin@empresa.cl', 'password': 'wrong'
        })
        assert resp.status_code == 401

    def test_login_email_inexistente(self, client):
        resp = client.post('/api/auth/login', json={
            'email': 'noexist@test.cl', 'password': 'admin123'
        })
        assert resp.status_code == 401

    def test_login_faltan_campos(self, client):
        resp = client.post('/api/auth/login', json={'email': 'admin@empresa.cl'})
        assert resp.status_code in (400, 401)

    # ── JWT /me ──────────────────────────────────────────
    def test_me_con_token_valido(self, client, admin_token):
        resp = client.get('/api/auth/me',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'user' in data
        assert data['user']['email'] == 'admin@empresa.cl'

    def test_me_sin_token(self, client):
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401

    def test_me_token_invalido(self, client):
        resp = client.get('/api/auth/me',
            headers={'Authorization': 'Bearer token.falso.aqui'})
        assert resp.status_code == 401

    def test_me_token_expirado(self, client):
        import jwt, time
        expired = jwt.encode(
            {'user_id': 1, 'empresa_id': 1, 'rol': 'admin', 'exp': time.time() - 3600},
            'test-jwt-secret-for-tests-only', algorithm='HS256'
        )
        resp = client.get('/api/auth/me',
            headers={'Authorization': f'Bearer {expired}'})
        assert resp.status_code == 401

    # ── Register ─────────────────────────────────────────
    def test_admin_puede_crear_empleador(self, client, admin_token):
        resp = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Nuevo Emp', 'email': 'nuevo@test.cl',
                  'password': 'test1234', 'rol': 'empleador', 'empresa_id': 1})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_empleador_puede_crear_trabajador(self, client, empleador_token):
        resp = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Trab', 'email': 'trab@test.cl',
                  'password': 'test1234', 'rol': 'trabajador', 'empresa_id': 2})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_trabajador_no_puede_crear_usuarios(self, client, trabajador_token):
        resp = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {trabajador_token}'},
            json={'nombre': 'X', 'email': 'x@test.cl',
                  'password': 'test1234', 'rol': 'trabajador'})
        assert resp.status_code in (401, 403)

    def test_register_sin_token(self, client):
        resp = client.post('/api/auth/register', json={
            'nombre': 'X', 'email': 'x@x.cl', 'password': '1234', 'rol': 'empleador'
        })
        assert resp.status_code == 401

    def test_register_email_duplicado(self, client, admin_token):
        resp = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'X', 'email': 'admin@empresa.cl',
                  'password': 'test1234', 'rol': 'empleador', 'empresa_id': 1})
        assert resp.status_code != 200

    # ── Register company (auto) ──────────────────────────
    def test_register_company_sin_token(self, client):
        resp = client.post('/api/auth/register-company', json={
            'empresa_nombre': 'Nueva Empresa Auto',
            'admin_nombre': 'Admin Auto',
            'admin_email': 'auto@test.cl',
            'admin_password': 'admin1234'
        })
        assert resp.status_code in (200, 201)
        data = resp.get_json()
        assert data['ok'] is True
        assert 'token' in data

    # ── Change password ─────────────────────────────────
    def test_change_password(self, client, admin_token):
        resp = client.put('/api/auth/change-password',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'password_actual': 'admin123', 'password_nueva': 'newpass123'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        login = client.post('/api/auth/login', json={
            'email': 'admin@empresa.cl', 'password': 'newpass123'
        })
        assert login.status_code == 200

    # ── Usuarios ─────────────────────────────────────────
    def test_listar_usuarios_admin(self, client, admin_token):
        resp = client.get('/api/auth/usuarios',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_listar_usuarios_empleador(self, client, empleador_token):
        resp = client.get('/api/auth/usuarios',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200

    # ── Empresas ─────────────────────────────────────────
    def test_admin_lista_empresas(self, client, admin_token):
        resp = client.get('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_admin_crea_empresa(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Nueva Empresa SA',
                'rut_empresa': '99.999.999-9',
                'mode': 'new',
                'nombre_usuario': 'Admin Nueva',
                'email_usuario': 'admin_nueva@test.cl',
                'password_usuario': 'test1234',
                'rol_usuario': 'empleador'
            })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_empleador_no_crea_empresa(self, client, empleador_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Empresa ilegal'})
        assert resp.status_code == 403

    # ── PIN y enrolamiento ──────────────────────────────
    def test_generar_pin_dispositivo(self, client, empleador_token):
        resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Reloj Test'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'pin' in data
        assert len(data['pin']) == 8

    def test_enrolar_dispositivo(self, client, empleador_token):
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Reloj Enrolable'})
        pin = pin_resp.get_json()['pin']
        resp = client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:FF', 'ip': '192.168.1.50'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_enrolar_pin_invalido(self, client, empleador_token):
        resp = client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'codigo': 'XXXXXXXX', 'mac': 'AA:BB:CC:DD:EE:FF', 'ip': '10.0.0.1'})
        assert resp.status_code == 404

    # ── Asignar usuario a empresa ───────────────────────
    def test_asignar_usuario_empresa(self, client, admin_token):
        resp = client.post('/api/auth/asignar-usuario',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'usuario_id': 1, 'empresa_id': 1, 'rol': 'empleador'})
        assert resp.status_code == 200

    # ── Eliminar usuario de empresa ──────────────────────
    def test_admin_elimina_usuario_de_empresa(self, client, admin_token):
        client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'A Borrar', 'email': 'borrar@test.cl',
                  'password': 'test1234', 'rol': 'empleador', 'empresa_id': 1})
        resp = client.delete('/api/auth/usuarios/2',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'empresa_id': 1})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_admin_elimina_usuario_inexistente(self, client, admin_token):
        resp = client.delete('/api/auth/usuarios/99999',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'empresa_id': 1})
        assert resp.status_code == 404

    def test_eliminar_usuario_sin_auth(self, client):
        resp = client.delete('/api/auth/usuarios/1')
        assert resp.status_code == 401

    def test_empleador_elimina_usuario_de_su_empresa(self, client, empleador_token):
        reg = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Trab Borrar', 'email': 'trab_borrar@test.cl',
                  'password': 'test1234', 'rol': 'trabajador', 'empresa_id': 2})
        uid = reg.get_json()['id']
        resp = client.delete(f'/api/auth/usuarios/{uid}',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'empresa_id': 2})
        assert resp.status_code == 200

    # ── Actualizar usuario ───────────────────────────────
    def test_admin_actualiza_usuario(self, client, admin_token):
        client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Edit Me', 'email': 'editar_me@test.cl',
                  'password': 'test1234', 'rol': 'empleador', 'empresa_id': 1})
        resp = client.put('/api/auth/usuarios/2',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Actualizado', 'empresa_id': 1})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_actualizar_usuario_no_encontrado(self, client, admin_token):
        resp = client.put('/api/auth/usuarios/99999',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Nope', 'empresa_id': 1})
        assert resp.status_code == 404

    def test_actualizar_usuario_sin_auth(self, client):
        resp = client.put('/api/auth/usuarios/1', json={'nombre': 'X'})
        assert resp.status_code == 401

    def test_empleador_actualiza_solo_trabajador(self, client, empleador_token):
        reg = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Trab Edit', 'email': 'trab_edit@test.cl',
                  'password': 'test1234', 'rol': 'trabajador', 'empresa_id': 2})
        uid = reg.get_json()['id']
        resp = client.put(f'/api/auth/usuarios/{uid}',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Editado', 'empresa_id': 2})
        assert resp.status_code == 200

    # ── Eliminar empresa ─────────────────────────────────
    def test_admin_elimina_empresa(self, client, admin_token):
        r = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'A Eliminar',
                'mode': 'new',
                'nombre_usuario': 'AEliminar',
                'email_usuario': 'aeliminar@test.cl',
                'password_usuario': 'test1234',
                'rol_usuario': 'empleador'
            })
        emp_id = r.get_json()['id']
        resp = client.delete(f'/api/auth/empresas/{emp_id}',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_eliminar_empresa_sin_auth(self, client):
        resp = client.delete('/api/auth/empresas/1')
        assert resp.status_code == 401

    def test_generar_pin_empleador_su_empresa(self, client, empleador_token):
        resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Reloj Emp'})
        assert resp.status_code == 200

    # ── Register company edge cases ──────────────────────
    def test_register_company_campos_faltantes(self, client):
        resp = client.post('/api/auth/register-company', json={'empresa_nombre': 'X'})
        assert resp.status_code == 400

    def test_register_company_password_corta(self, client):
        resp = client.post('/api/auth/register-company', json={
            'empresa_nombre': 'X', 'admin_nombre': 'A', 'admin_email': 'a@b.cl', 'admin_password': 'ab'
        })
        assert resp.status_code == 400

    def test_register_company_email_invalido(self, client):
        resp = client.post('/api/auth/register-company', json={
            'empresa_nombre': 'X', 'admin_nombre': 'A', 'admin_email': 'no-arroba', 'admin_password': 'test1234'
        })
        assert resp.status_code == 400

    # ── Change password edge cases ───────────────────────
    def test_change_password_wrong_actual(self, client, admin_token):
        resp = client.put('/api/auth/change-password',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'password_actual': 'wrongpass', 'password_nueva': 'newpass123'})
        assert resp.status_code == 401

    def test_change_password_campos_faltantes(self, client, admin_token):
        resp = client.put('/api/auth/change-password',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'password_actual': 'admin123'})
        assert resp.status_code == 400

    def test_change_password_corta(self, client, admin_token):
        resp = client.put('/api/auth/change-password',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'password_actual': 'admin123', 'password_nueva': 'ab'})
        assert resp.status_code == 400

    # ── Login edge cases ──────────────────────────────────
    def test_login_usuario_desactivado(self, client, admin_token):
        from database import get_connection
        client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Desactivar', 'email': 'desact@test.cl',
                  'password': 'test1234', 'rol': 'empleador', 'empresa_id': 1})
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE usuarios_web SET activo = FALSE WHERE email = 'desact@test.cl'")
        conn.commit()
        cur.close()
        conn.close()
        resp = client.post('/api/auth/login', json={
            'email': 'desact@test.cl', 'password': 'test1234', 'empresa_id': 1})
        assert resp.status_code == 403

    def test_login_need_empresa_multi_empresa(self, client, admin_token):
        create = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Empresa B',
                'rut_empresa': '88.888.888-8',
                'mode': 'new',
                'nombre_usuario': 'Admin B',
                'email_usuario': 'admin_b_999@test.cl',
                'password_usuario': 'test1234',
                'rol_usuario': 'empleador'
            })
        emp_id = create.get_json()['id']
        client.post('/api/auth/asignar-usuario',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'usuario_id': 1, 'empresa_id': emp_id, 'rol': 'empleador'})
        resp = client.post('/api/auth/login', json={
            'email': 'admin@empresa.cl', 'password': 'admin123'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is False
        assert data['need_empresa'] is True
        assert len(data['empresas']) >= 2

    def test_login_empresa_no_valida(self, client, admin_token):
        create = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Empresa X',
                'rut_empresa': '66.666.666-6',
                'mode': 'new',
                'nombre_usuario': 'Admin X',
                'email_usuario': 'admin_x_888@test.cl',
                'password_usuario': 'test1234',
                'rol_usuario': 'empleador'
            })
        emp_id = create.get_json()['id']
        client.post('/api/auth/asignar-usuario',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'usuario_id': 1, 'empresa_id': emp_id, 'rol': 'empleador'})
        resp = client.post('/api/auth/login', json={
            'email': 'admin@empresa.cl', 'password': 'admin123', 'empresa_id': 99999})
        assert resp.status_code == 403

    # ── Register validation errors ────────────────────────
    def test_register_faltan_campos(self, client, admin_token):
        resp = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'X'})
        assert resp.status_code == 400

    def test_register_rol_invalido(self, client, admin_token):
        resp = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'X', 'email': 'x@x.cl',
                  'password': 'test1234', 'rol': 'superadmin', 'empresa_id': 1})
        assert resp.status_code == 400

    def test_register_sin_permisos_rol(self, client, empleador_token):
        resp = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'X', 'email': 'x2@x.cl',
                  'password': 'test1234', 'rol': 'admin', 'empresa_id': 2})
        assert resp.status_code == 403

    def test_register_admin_sin_empresa_id(self, client, admin_token):
        resp = client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'X', 'email': 'x3@x.cl',
                  'password': 'test1234', 'rol': 'trabajador'})
        assert resp.status_code == 400

    # ── Register company duplicate email ──────────────────
    def test_register_company_email_duplicado(self, client):
        resp = client.post('/api/auth/register-company', json={
            'empresa_nombre': 'Duplicado',
            'admin_nombre': 'Admin Dup',
            'admin_email': 'admin@empresa.cl',
            'admin_password': 'test1234'
        })
        assert resp.status_code == 409

    # ── Delete user edge cases ────────────────────────────
    def test_admin_se_remueve_de_empresa(self, client, admin_token):
        create = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={
                'nombre': 'Temporary',
                'rut_empresa': '77.777.777-7',
                'mode': 'new',
                'nombre_usuario': 'Admin Temp',
                'email_usuario': 'admin_temp_777@test.cl',
                'password_usuario': 'test1234',
                'rol_usuario': 'empleador'
            })
        emp_id = create.get_json()['id']
        client.post('/api/auth/asignar-usuario',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'usuario_id': 1, 'empresa_id': emp_id, 'rol': 'empleador'})
        resp = client.delete('/api/auth/usuarios/1',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'empresa_id': emp_id})
        assert resp.status_code == 200

    def test_delete_usuario_sin_permisos(self, client, empleador_token):
        resp = client.delete('/api/auth/usuarios/1',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'empresa_id': 1})
        assert resp.status_code in (403, 404)

    # ── Edit user edge cases ──────────────────────────────
    def test_edit_usuario_sin_permisos(self, client, empleador_token):
        resp = client.put('/api/auth/usuarios/1',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Hack', 'empresa_id': 1})
        assert resp.status_code in (403, 404)

    def test_edit_usuario_password_y_activo(self, client, admin_token):
        client.post('/api/auth/register',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Full Edit', 'email': 'full@test.cl',
                  'password': 'test1234', 'rol': 'empleador', 'empresa_id': 1})
        resp = client.put('/api/auth/usuarios/2',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'email': 'full2@test.cl', 'password': 'newpass456',
                  'activo': True, 'empresa_id': 1})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    # ── Create empresa edge cases ─────────────────────────
    def test_crear_empresa_sin_nombre(self, client, admin_token):
        resp = client.post('/api/auth/empresas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'rut_empresa': '66.666.666-6'})
        assert resp.status_code == 400

    # ── Assign usuario edge cases ─────────────────────────
    def test_asignar_faltan_campos(self, client, admin_token):
        resp = client.post('/api/auth/asignar-usuario',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'usuario_id': 1})
        assert resp.status_code == 400

    def test_asignar_rol_invalido(self, client, admin_token):
        resp = client.post('/api/auth/asignar-usuario',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'usuario_id': 1, 'empresa_id': 1, 'rol': 'owner'})
        assert resp.status_code == 400

    # ── Device PIN edge cases ─────────────────────────────
    def test_enrolar_pin_ya_usado(self, client, empleador_token):
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'Reloj 1'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:11', 'ip': '10.0.0.1'})
        resp = client.post('/api/auth/dispositivos/enrolar',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'codigo': pin, 'mac': 'AA:BB:CC:DD:EE:22', 'ip': '10.0.0.2'})
        assert resp.status_code != 200


