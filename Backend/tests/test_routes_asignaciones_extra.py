"""Tests adicionales para routes/asignaciones.py.

Cubre tres ramas que no tenian cobertura:
  - GET /api/asignaciones con rol 'empleador' (linea 30).
  - GET /api/asignaciones con rol 'trabajador' y persona_id en el JWT (linea 39).
    El fixture `trabajador_token` de conftest.py no sirve para esto: crea la
    persona con un email distinto al del usuario de login, por lo que el
    backend nunca encuentra el persona_id al iniciar sesion y el JWT termina
    sin 'persona_id'. Por eso se construye aqui un token manualmente.
  - POST /api/asignaciones sin persona_id y sin rut (linea 92).
"""
import datetime
import jwt


def _token_trabajador_con_persona(empresa_id, persona_id):
    from routes.auth import JWT_SECRET
    payload = {
        'user_id': 9999,
        'empresa_id': empresa_id,
        'rol': 'trabajador',
        'persona_id': persona_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


class TestAsignacionesGetRoles:

    def test_get_asignaciones_empleador(self, client, empleador_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'P Emp Get', 'rut': '15.000.000-1'})
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'nombre': 'T-Emp', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {empleador_token}'},
            json={'persona_id': '1', 'turno_id': str(t.get_json()['id'])})

        resp = client.get('/api/asignaciones',
            headers={'Authorization': f'Bearer {empleador_token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_asignaciones_trabajador_con_persona_id_en_jwt(self, client, admin_token):
        p = client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Trabajador Real', 'rut': '16.000.000-2'})
        persona_id = p.get_json()['id']
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-Trab', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'persona_id': str(persona_id), 'turno_id': str(t.get_json()['id'])})

        token = _token_trabajador_con_persona(empresa_id=1, persona_id=persona_id)
        resp = client.get('/api/asignaciones',
            headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(a['persona_id'] == persona_id for a in data)
        assert len(data) >= 1


class TestCrearAsignacionSinDatos:

    def test_crear_asignacion_sin_persona_id_ni_rut(self, client, admin_token):
        t = client.post('/api/turnos',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'T-SinDatos', 'inicio': '08:00', 'fin': '17:00', 'dias': 'L'})
        resp = client.post('/api/asignaciones',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'turno_id': str(t.get_json()['id'])})
        assert resp.status_code == 400
        assert 'persona_id o rut' in resp.get_json()['error']
