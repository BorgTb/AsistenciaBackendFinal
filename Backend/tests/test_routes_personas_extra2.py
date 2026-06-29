"""Tests adicionales para routes/personas.py.

Cubre: _email_valido(None), listado por dispositivo (ESP32) con y sin
empresa asociada, consentimiento al crear persona, ramas de error/empresa
en merge/biometrico/update/huella/consentimiento/delete/datos-biometricos, y
la eliminacion fisica de archivos de preview.
"""
import datetime
import os
from unittest.mock import MagicMock, patch

import jwt


def _token_empleador(empresa_id=2):
    from routes.auth import JWT_SECRET
    payload = {
        'user_id': 8888,
        'empresa_id': empresa_id,
        'rol': 'empleador',
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def _token_trabajador(empresa_id, persona_id):
    from routes.auth import JWT_SECRET
    payload = {
        'user_id': 8889,
        'empresa_id': empresa_id,
        'rol': 'trabajador',
        'persona_id': persona_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def _enrolar_dispositivo(client, token, nombre='DispPersonas', mac='BB:CC:DD:EE:FF:01', ip='10.2.0.1'):
    pin_resp = client.post('/api/auth/dispositivos/generar-pin',
        headers={'Authorization': f'Bearer {token}'},
        json={'nombre': nombre})
    pin = pin_resp.get_json()['pin']
    enrol_resp = client.post('/api/auth/dispositivos/enrolar', json={
        'codigo': pin, 'mac': mac, 'ip': ip
    })
    return enrol_resp.get_json()['dispositivo_id']


class TestEmailValido:
    def test_email_valido_none(self):
        from routes.personas import _email_valido
        assert _email_valido(None) is True


class TestGetPersonasPorRol:

    def test_get_personas_trabajador_con_persona_id(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Trab Real', 'rut': '26.000.000-1'})
        persona_id = p.get_json()['id']
        token = _token_trabajador(empresa_id=1, persona_id=persona_id)
        resp = client.get('/api/personas', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['id'] == str(persona_id)

    def test_get_personas_dispositivo_con_empresa(self, client, admin_token):
        _enrolar_dispositivo(client, admin_token, mac='BB:CC:DD:EE:FF:02', ip='10.2.0.2')
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Por Disp', 'rut': '26.000.000-2'})
        resp = client.get('/api/personas', headers={'X-Device-MAC': 'BB:CC:DD:EE:FF:02'})
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_personas_dispositivo_sin_empresa_huerfanas(self, app):
        """Cubre las lineas 50-60: dispositivo con dispositivo_id seteado
        pero sin empresa_id resuelta. Se simula con la DB mockeada porque
        en la practica un dispositivo enrolado siempre tiene empresa_id."""
        from routes.personas import get_personas
        with app.test_request_context('/api/personas'):
            from flask import request
            request.user_rol = None
            request.empresa_id = None
            request.persona_id = None
            request.dispositivo_id = 42

            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_conn.cursor.return_value = mock_cur
            # 1) chequeo de dispositivo enrolado -> no encontrado
            mock_cur.fetchone.return_value = None
            mock_cur.fetchall.return_value = []
            with patch('routes.personas.get_connection', return_value=mock_conn):
                resp = get_personas.__wrapped__()
                assert resp.status_code == 200


class TestCreatePersonaConsentimiento:
    def test_crear_persona_con_consentimiento(self, client, admin_token):
        resp = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Con Consentimiento', 'rut': '26.000.000-3', 'consentimiento': True})
        assert resp.status_code == 200
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM consentimientos WHERE persona_id = %s",
                    (resp.get_json()['id'],))
        assert cur.fetchone() is not None
        cur.close()
        conn.close()


class TestDuplicadosYMergeErrores:

    def test_duplicados_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception('DB error')
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.get('/api/personas/duplicados',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500

    def test_merge_transfiere_huella_de_eliminar(self, client, admin_token):
        c1 = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Sin Huella', 'rut': '26.000.000-4'})
        id1 = c1.get_json()['id']
        c2 = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Con Huella', 'rut': '26.000.000-5'})
        id2 = c2.get_json()['id']
        client.put(f'/api/personas/{id2}/huella',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'huella_id': 5})

        resp = client.post('/api/personas/merge',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'mantener_id': id1, 'eliminar_id': id2})
        assert resp.status_code == 200

        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT huella_id FROM personas WHERE id = %s", (id1,))
        assert cur.fetchone()[0] == 5
        cur.close()
        conn.close()

    def test_merge_cache_invalidacion_excepcion_no_rompe(self, client, admin_token):
        c1 = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'M1', 'rut': '26.000.000-6'})
        c2 = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'M2', 'rut': '26.000.000-7'})
        with patch('routes.facial._invalidar_cache', side_effect=Exception('cache caida')):
            resp = client.post('/api/personas/merge',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'mantener_id': c1.get_json()['id'], 'eliminar_id': c2.get_json()['id']})
        assert resp.status_code == 200

    def test_merge_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.side_effect = [(1,), (2,), Exception('DB error')]
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.post('/api/personas/merge',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'mantener_id': 1, 'eliminar_id': 2})
            assert resp.status_code == 500
            mock_conn.rollback.assert_called_once()


class TestBiometricoExcepcion:
    def test_biometrico_db_error(self, client, admin_token):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.side_effect = Exception('DB error')
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.get('/api/personas/1/biometrico',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500


class TestUpdatePersonaRamas:

    def test_update_nombre_vacio(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Vacio', 'rut': '26.000.000-8'})
        resp = client.put(f"/api/personas/{p.get_json()['id']}",
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': '   '})
        assert resp.status_code == 400

    def test_update_sin_campos(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P SinCampos', 'rut': '26.000.000-9'})
        resp = client.put(f"/api/personas/{p.get_json()['id']}",
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 400

    def test_update_persona_empleador_su_empresa(self, client, empleador_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Emp Upd', 'rut': '26.000.001-0'})
        resp = client.put(f"/api/personas/{p.get_json()['id']}",
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Emp Upd Actualizado'})
        assert resp.status_code == 200


class TestUpdateHuellaRamas:

    def test_update_huella_sin_huella_id_key(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Huella Falta', 'rut': '26.000.001-1'})
        resp = client.put(f"/api/personas/{p.get_json()['id']}/huella",
            headers={'Authorization': f'Bearer {admin_token}'},
            json={})
        assert resp.status_code == 400

    def test_update_huella_empleador_su_empresa(self, client, empleador_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Emp Huella', 'rut': '26.000.001-2'})
        resp = client.put(f"/api/personas/{p.get_json()['id']}/huella",
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'huella_id': 7})
        assert resp.status_code == 200

    def test_update_huella_db_error(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Huella Err', 'rut': '26.000.001-3'})
        persona_id = p.get_json()['id']
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.side_effect = [(persona_id,), None, Exception('DB error')]
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.put(f'/api/personas/{persona_id}/huella',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={'huella_id': 8})
            assert resp.status_code == 500


class TestConsentimientoRamas:

    def test_consentimiento_empleador_su_empresa(self, client, empleador_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Emp Cons', 'rut': '26.000.001-4'})
        resp = client.post(f"/api/personas/{p.get_json()['id']}/consentimiento",
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={})
        assert resp.status_code == 200

    def test_consentimiento_db_error(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Cons Err', 'rut': '26.000.001-5'})
        persona_id = p.get_json()['id']
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (persona_id,)
        mock_cur.execute.side_effect = [None, Exception('DB error')]
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.post(f'/api/personas/{persona_id}/consentimiento',
                headers={'Authorization': f'Bearer {admin_token}'},
                json={})
            assert resp.status_code == 500


class TestDeletePersonaRamas:

    def test_delete_persona_admin_elimina_foto_preview(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Foto', 'rut': '26.000.001-6'})
        persona_id = p.get_json()['id']

        from routes.personas import PREVIEWS_DIR
        os.makedirs(PREVIEWS_DIR, exist_ok=True)
        foto_path = os.path.join(PREVIEWS_DIR, f'{persona_id}.jpg')
        with open(foto_path, 'wb') as f:
            f.write(b'fake-image-bytes')

        resp = client.delete(f'/api/personas/{persona_id}',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert not os.path.exists(foto_path)

    def test_delete_persona_cache_invalidacion_excepcion_no_rompe(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P CacheDel', 'rut': '26.000.001-7'})
        with patch('routes.facial._invalidar_cache', side_effect=Exception('cache caida')):
            resp = client.delete(f"/api/personas/{p.get_json()['id']}",
                headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_delete_persona_empleador_otra_empresa_404(self, client, admin_token, empleador_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Admin', 'rut': '26.000.001-8'})
        resp = client.delete(f"/api/personas/{p.get_json()['id']}",
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 404

    def test_delete_persona_sin_autorizacion(self, client):
        resp = client.delete('/api/personas/1')
        assert resp.status_code == 403


class TestEliminarDatosBiometricosRamas:

    def test_eliminar_biometricos_empleador_su_empresa(self, client, empleador_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Emp Bio', 'rut': '26.000.001-9'})
        resp = client.delete(f"/api/personas/{p.get_json()['id']}/datos-biometricos",
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200

    def test_eliminar_biometricos_elimina_foto_preview(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Bio Foto', 'rut': '26.000.002-0'})
        persona_id = p.get_json()['id']

        from routes.personas import PREVIEWS_DIR
        os.makedirs(PREVIEWS_DIR, exist_ok=True)
        foto_path = os.path.join(PREVIEWS_DIR, f'{persona_id}.jpg')
        with open(foto_path, 'wb') as f:
            f.write(b'fake-image-bytes')

        resp = client.delete(f'/api/personas/{persona_id}/datos-biometricos',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200
        assert not os.path.exists(foto_path)

    def test_eliminar_biometricos_cache_invalidacion_excepcion_no_rompe(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Bio Cache', 'rut': '26.000.002-1'})
        with patch('routes.facial._invalidar_cache', side_effect=Exception('cache caida')):
            resp = client.delete(f"/api/personas/{p.get_json()['id']}/datos-biometricos",
                headers={'Authorization': f'Bearer {admin_token}'})
        assert resp.status_code == 200

    def test_eliminar_biometricos_db_error(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Bio Err', 'rut': '26.000.002-2'})
        persona_id = p.get_json()['id']
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.side_effect = [(persona_id, 'P Bio Err'), Exception('DB error')]
        with patch('routes.personas.get_connection', return_value=mock_conn):
            resp = client.delete(f'/api/personas/{persona_id}/datos-biometricos',
                headers={'Authorization': f'Bearer {admin_token}'})
            assert resp.status_code == 500
