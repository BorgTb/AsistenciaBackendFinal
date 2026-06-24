import bcrypt
from database import get_connection, resolver_rut_a_id


class TestResolverRut:
    """Tests para resolver_rut_a_id."""

    def test_rut_vacio_retorna_none(self, app):
        assert resolver_rut_a_id('') is None
        assert resolver_rut_a_id(None) is None

    def test_rut_no_existente_retorna_none(self, app):
        assert resolver_rut_a_id('99.999.999-9') is None

    def test_rut_existente_retorna_id(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO personas (nombre, rut, email, empresa_id) "
            "VALUES ('Test Persona', '12.345.678-9', 'test@test.cl', 1) "
            "RETURNING id"
        )
        persona_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        result = resolver_rut_a_id('12.345.678-9')
        assert result == persona_id

    def test_rut_excepcion_db_retorna_none(self, app):
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('database.get_connection', return_value=mock_conn):
            result = resolver_rut_a_id('12.345.678-9')
            assert result is None


class TestDatabase:
    """Tests de esquema y seed de la base de datos."""

    def test_all_tables_exist(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' ORDER BY tablename"
        )
        tables = {row[0] for row in cur.fetchall()}
        expected = {
            'empresas', 'dispositivos', 'usuarios_web', 'usuario_empresa',
            'personas', 'turnos', 'asignaciones', 'asistencias',
            'sincronizacion_log', 'integraciones_erp',
            'consentimientos', 'logs_biometricos', 'eliminaciones_biometricas',
            'encodings_faciales'
        }
        missing = expected - tables
        cur.close()
        conn.close()
        assert not missing, f"Tablas faltantes: {missing}"

    def test_seed_empresa_default(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM empresas WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[1] == 'Empresa por defecto'

    def test_seed_admin_user_exists(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, email, nombre FROM usuarios_web WHERE email = 'admin@empresa.cl'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[1] == 'admin@empresa.cl'
        assert row[2] == 'Administrador'

    def test_admin_has_role_admin(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT ue.rol FROM usuario_empresa ue
            JOIN usuarios_web uw ON uw.id = ue.usuario_id
            WHERE uw.email = 'admin@empresa.cl' AND ue.empresa_id = 1
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        assert row[0] == 'admin'

    def test_admin_password_is_bcrypt(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM usuarios_web WHERE email = 'admin@empresa.cl'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None
        pwd = row[0]
        assert pwd.startswith('$2b$') or pwd.startswith('$2a$')

    def test_admin_login_succeeds_with_password(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM usuarios_web WHERE email = 'admin@empresa.cl'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert bcrypt.checkpw('admin123'.encode('utf-8'), row[0].encode('utf-8'))

    def test_column_migrations_personas(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'personas'
        """)
        cols = {row[0] for row in cur.fetchall()}
        required = {'id', 'empresa_id', 'nombre', 'rut', 'email',
                    'huella_id', 'activo', 'created_at'}
        missing = required - cols
        cur.close()
        conn.close()
        assert not missing, f"Columnas faltantes en personas: {missing}"

    def test_column_migrations_dispositivos(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'dispositivos'
        """)
        cols = {row[0] for row in cur.fetchall()}
        assert 'codigo_enrol' in cols
        assert 'enrolado' in cols
        cur.close()
        conn.close()

    def test_init_db_is_idempotent(self, app):
        from database import init_db
        init_db()
        init_db()
        init_db()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM empresas WHERE id = 1")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        assert count == 1

    def test_fresh_db_has_no_extra_data(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM personas")
        personas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM asistencias")
        asistencias = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM turnos")
        turnos = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dispositivos")
        dispositivos = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM integraciones_erp")
        erps = cur.fetchone()[0]
        cur.close()
        conn.close()
        assert personas == 0
        assert asistencias == 0
        assert turnos == 0
        assert dispositivos == 0
        assert erps == 0

    def test_init_db_exception_handler(self, app):
        """Cubre el except block de init_db que imprime traceback y relanza."""
        from unittest.mock import patch, MagicMock
        import pytest
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('Schema creation error')
        with patch('database.get_connection', return_value=mock_conn):
            with pytest.raises(Exception, match='Schema creation error'):
                from database import init_db
                init_db()
            mock_conn.rollback.assert_not_called()  # init_db no usa rollback, solo propaga
