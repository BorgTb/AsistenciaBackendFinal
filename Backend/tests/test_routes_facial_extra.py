"""Tests adicionales para routes/facial.py.

El proyecto mockea globalmente `cv2` y `deepface` en conftest.py (para no
cargar modelos de ML reales en cada test), con valores fijos que siempre
indican "imagen nitida" y "rostro detectado". Eso significa que, por
defecto, ninguna prueba existente jamas ejercita las ramas de error de
calidad de imagen ni de fallo de deteccion facial. Aqui se sobreescriben
esos mocks puntualmente (cv2.imread, cv2.Laplacian, DeepFace.represent)
para forzar esas ramas sin depender de un modelo real.

Tambien se cubren rutas alternativas (octet-stream, resolucion por RUT)
que existen en el codigo pero no estaban ejercitadas por ningun test.
"""
import io
import base64
from unittest.mock import patch, MagicMock

from PIL import Image


def _b64_dummy_jpeg():
    img = Image.new('RGB', (16, 16), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _raw_dummy_jpeg():
    return base64.b64decode(_b64_dummy_jpeg())


class TestHelpersDirectos:
    """Funciones auxiliares testeadas directamente."""

    def test_resolver_persona_id_sin_datos(self):
        from routes.facial import _resolver_persona_id
        assert _resolver_persona_id({}) is None

    def test_resolver_persona_id_por_rut(self, app, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Rut Resolv', 'rut': '60.000.000-1'})
        from routes.facial import _resolver_persona_id
        with app.test_request_context():
            pid = _resolver_persona_id({'rut': '60.000.000-1'})
        assert pid is not None

    def test_validar_calidad_imagen_no_se_pudo_leer(self):
        from routes.facial import _validar_calidad_imagen
        with patch('cv2.imread', return_value=None):
            ok, msg, score = _validar_calidad_imagen('/ruta/inexistente.jpg')
        assert ok is False
        assert 'No se pudo leer' in msg
        assert score == 0.0

    def test_validar_calidad_imagen_baja_nitidez(self):
        from routes.facial import _validar_calidad_imagen
        import cv2
        original_var = cv2.Laplacian.return_value.var.return_value
        cv2.Laplacian.return_value.var.return_value = 5.0
        try:
            ok, msg, score = _validar_calidad_imagen('/cualquier/ruta.jpg')
        finally:
            cv2.Laplacian.return_value.var.return_value = original_var
        assert ok is False
        assert 'baja nitidez' in msg

    def test_guardar_imagen_temporal_sin_b64(self):
        from routes.facial import guardar_imagen_temporal
        assert guardar_imagen_temporal(None) is None
        assert guardar_imagen_temporal('') is None

    def test_guardar_imagen_temporal_con_b64(self):
        from routes.facial import guardar_imagen_temporal
        import os
        path = guardar_imagen_temporal(_b64_dummy_jpeg())
        assert path is not None
        assert os.path.exists(path)
        os.unlink(path)

    def test_log_biometrico_excepcion_no_rompe(self):
        from routes.facial import _log_biometrico
        with patch('routes.facial.get_connection', side_effect=Exception('db caida')):
            _log_biometrico(1, None, 'registro', 'exito')


class TestRegistrarFacialRamasAdicionales:

    def test_registrar_octet_stream_sin_rut(self, client):
        resp = client.post('/api/facial/registrar',
            data=_raw_dummy_jpeg(), content_type='application/octet-stream')
        assert resp.status_code == 400
        assert 'X-RUT' in resp.get_json()['error']

    def test_registrar_octet_stream_con_rut_exitoso(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Octet', 'rut': '60.000.000-2'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.post('/api/facial/registrar',
            data=_raw_dummy_jpeg(), content_type='application/octet-stream',
            headers={'X-RUT': '60.000.000-2'})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_registrar_json_base64_invalido(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P B64', 'rut': '60.000.000-3'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': 'A'
        })
        assert resp.status_code == 400

    def test_registrar_persona_no_encontrada_por_rut(self, client):
        resp = client.post('/api/facial/registrar', json={
            'rut': '60.999.999-9', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 404

    def test_registrar_calidad_insuficiente(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Calidad', 'rut': '60.000.000-4'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        import cv2
        original = cv2.Laplacian.return_value.var.return_value
        cv2.Laplacian.return_value.var.return_value = 1.0
        try:
            resp = client.post('/api/facial/registrar', json={
                'persona_id': '1', 'imagen': _b64_dummy_jpeg()
            })
        finally:
            cv2.Laplacian.return_value.var.return_value = original
        assert resp.status_code == 400

    def test_registrar_deepface_no_detecta_rostro(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P NoFace', 'rut': '60.000.000-5'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        with patch('deepface.DeepFace.represent', side_effect=ValueError('Face could not be detected')):
            resp = client.post('/api/facial/registrar', json={
                'persona_id': '1', 'imagen': _b64_dummy_jpeg()
            })
        assert resp.status_code == 400

    def test_registrar_excepcion_generica(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P ExcGen', 'rut': '60.000.000-6'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        with patch('deepface.DeepFace.represent', side_effect=RuntimeError('modelo caido')):
            resp = client.post('/api/facial/registrar', json={
                'persona_id': '1', 'imagen': _b64_dummy_jpeg()
            })
        assert resp.status_code == 500


class TestAgregarFotoRamasAdicionales:

    def test_agregar_foto_octet_stream_sin_rut(self, client):
        resp = client.post('/api/facial/agregar-foto',
            data=_raw_dummy_jpeg(), content_type='application/octet-stream')
        assert resp.status_code == 400

    def test_agregar_foto_octet_stream_exitoso(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Foto Octet', 'rut': '60.000.000-7'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        resp = client.post('/api/facial/agregar-foto',
            data=_raw_dummy_jpeg(), content_type='application/octet-stream',
            headers={'X-RUT': '60.000.000-7'})
        assert resp.status_code == 200

    def test_agregar_foto_json_base64_invalido(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Foto B64', 'rut': '60.000.000-8'})
        resp = client.post('/api/facial/agregar-foto', json={
            'persona_id': '1', 'imagen': 'no-es-base64!!!'
        })
        assert resp.status_code == 400

    def test_agregar_foto_persona_no_encontrada(self, client):
        resp = client.post('/api/facial/agregar-foto', json={
            'rut': '60.999.999-8', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 404

    def test_agregar_foto_calidad_insuficiente(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Foto Calidad', 'rut': '60.000.000-9'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        import cv2
        original = cv2.Laplacian.return_value.var.return_value
        cv2.Laplacian.return_value.var.return_value = 1.0
        try:
            resp = client.post('/api/facial/agregar-foto', json={
                'persona_id': '1', 'imagen': _b64_dummy_jpeg()
            })
        finally:
            cv2.Laplacian.return_value.var.return_value = original
        assert resp.status_code == 400

    def test_agregar_foto_deepface_no_detecta_rostro(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Foto NoFace', 'rut': '60.000.001-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        with patch('deepface.DeepFace.represent', side_effect=ValueError('no face')):
            resp = client.post('/api/facial/agregar-foto', json={
                'persona_id': '1', 'imagen': _b64_dummy_jpeg()
            })
        assert resp.status_code == 400

    def test_agregar_foto_excepcion_generica(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Foto ExcGen', 'rut': '60.000.001-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        with patch('deepface.DeepFace.represent', side_effect=RuntimeError('modelo caido')):
            resp = client.post('/api/facial/agregar-foto', json={
                'persona_id': '1', 'imagen': _b64_dummy_jpeg()
            })
        assert resp.status_code == 500


class TestActualizarFacialRamasAdicionales:

    def test_actualizar_facial_por_rut_no_encontrado(self, client):
        resp = client.put('/api/facial/actualizar/1', json={
            'imagen': _b64_dummy_jpeg(), 'rut': '60.999.999-7'
        })
        assert resp.status_code == 404

    def test_actualizar_facial_por_rut_exitoso(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Act Rut', 'rut': '60.000.001-2'})
        resp = client.put('/api/facial/actualizar/1', json={
            'imagen': _b64_dummy_jpeg(), 'rut': '60.000.001-2'
        })
        assert resp.status_code == 200

    def test_actualizar_facial_calidad_insuficiente(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Act Calidad', 'rut': '60.000.001-3'})
        import cv2
        original = cv2.Laplacian.return_value.var.return_value
        cv2.Laplacian.return_value.var.return_value = 1.0
        try:
            resp = client.put('/api/facial/actualizar/1', json={'imagen': _b64_dummy_jpeg()})
        finally:
            cv2.Laplacian.return_value.var.return_value = original
        assert resp.status_code == 400

    def test_actualizar_facial_deepface_no_detecta_rostro(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Act NoFace', 'rut': '60.000.001-4'})
        with patch('deepface.DeepFace.represent', side_effect=ValueError('no face')):
            resp = client.put('/api/facial/actualizar/1', json={'imagen': _b64_dummy_jpeg()})
        assert resp.status_code == 400

    def test_actualizar_facial_excepcion_generica(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Act ExcGen', 'rut': '60.000.001-5'})
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (1,)
        mock_cur.execute.side_effect = [None, Exception('DB error')]
        with patch('routes.facial.get_connection', return_value=mock_conn):
            resp = client.put('/api/facial/actualizar/1', json={'imagen': _b64_dummy_jpeg()})
        assert resp.status_code == 500


class TestVerificarFacialRamasAdicionales:

    def test_verificar_persona_no_encontrada_por_rut(self, client):
        resp = client.post('/api/facial/verificar', json={
            'rut': '60.999.999-6', 'imagen': _b64_dummy_jpeg()
        })
        assert resp.status_code == 404

    def test_verificar_calidad_insuficiente(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ver Calidad', 'rut': '60.000.001-6'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})

        import cv2
        original = cv2.Laplacian.return_value.var.return_value
        cv2.Laplacian.return_value.var.return_value = 1.0
        try:
            resp = client.post('/api/facial/verificar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})
        finally:
            cv2.Laplacian.return_value.var.return_value = original
        assert resp.status_code == 400

    def test_verificar_encoding_corrupto_se_ignora(self, client, admin_token):
        """Un encoding que no se puede descifrar se ignora silenciosamente
        (except Exception: pass dentro del loop de comparacion)."""
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ver Corrupto', 'rut': '60.000.001-7'})
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO encodings_faciales (persona_id, encoding, quality_score) VALUES (%s, %s, %s)",
            (1, 'esto-no-es-un-encoding-cifrado-valido', 100.0)
        )
        conn.commit()
        cur.close()
        conn.close()

        resp = client.post('/api/facial/verificar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})
        assert resp.status_code == 404

    def test_verificar_deepface_no_detecta_rostro(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ver NoFace', 'rut': '60.000.001-8'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})
        with patch('deepface.DeepFace.represent', side_effect=ValueError('no face')):
            resp = client.post('/api/facial/verificar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})
        assert resp.status_code == 400

    def test_verificar_excepcion_generica(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ver ExcGen', 'rut': '60.000.001-9'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})
        with patch('deepface.DeepFace.represent', side_effect=RuntimeError('modelo caido')):
            resp = client.post('/api/facial/verificar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})
        assert resp.status_code == 500


class TestIdentificarFacialRamasAdicionales:

    def test_identificar_sin_content_type_con_datos(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ident SinCT', 'rut': '60.000.002-0'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})

        resp = client.post('/api/facial/identificar', data=_raw_dummy_jpeg())
        assert resp.status_code in (200, 415)

    def test_identificar_json_sin_imagen_con_content_type_json(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ident SinImg', 'rut': '60.000.002-1'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})

        resp = client.post('/api/facial/identificar', json={}, content_type='application/json')
        assert resp.status_code == 400

    def test_identificar_calidad_insuficiente(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ident Calidad', 'rut': '60.000.002-2'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})

        import cv2
        original = cv2.Laplacian.return_value.var.return_value
        cv2.Laplacian.return_value.var.return_value = 1.0
        try:
            resp = client.post('/api/facial/identificar',
                json={'imagen': _b64_dummy_jpeg()}, content_type='application/json')
        finally:
            cv2.Laplacian.return_value.var.return_value = original
        assert resp.status_code == 400

    def test_identificar_no_coincide_con_nadie(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ident NoMatch', 'rut': '60.000.002-3'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})

        with patch('deepface.DeepFace.represent', return_value=[{'embedding': [99.0] * 128}]):
            resp = client.post('/api/facial/identificar',
                json={'imagen': _b64_dummy_jpeg()}, content_type='application/json')
        assert resp.status_code == 404
        assert 'no reconocido' in resp.get_json()['error']

    def test_identificar_deepface_no_detecta_rostro(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ident NoFace', 'rut': '60.000.002-4'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})

        with patch('deepface.DeepFace.represent', side_effect=ValueError('no face')):
            resp = client.post('/api/facial/identificar',
                json={'imagen': _b64_dummy_jpeg()}, content_type='application/json')
        assert resp.status_code == 400

    def test_identificar_excepcion_generica(self, client, admin_token):
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P Ident ExcGen', 'rut': '60.000.002-5'})
        client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        client.post('/api/facial/registrar', json={'persona_id': '1', 'imagen': _b64_dummy_jpeg()})

        with patch('deepface.DeepFace.represent', side_effect=RuntimeError('modelo caido')):
            resp = client.post('/api/facial/identificar',
                json={'imagen': _b64_dummy_jpeg()}, content_type='application/json')
        assert resp.status_code == 500


class TestIdentificarORegistrarRamasAdicionales:

    def test_identificar_o_registrar_calidad_insuficiente(self, client):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        import cv2
        original = cv2.Laplacian.return_value.var.return_value
        cv2.Laplacian.return_value.var.return_value = 1.0
        try:
            resp = client.post('/api/facial/identificar-o-registrar', json={
                'imagen': _b64_dummy_jpeg()
            })
        finally:
            cv2.Laplacian.return_value.var.return_value = original
        assert resp.status_code == 400

    def test_identificar_o_registrar_con_mac_crea_dispositivo_origen(self, client, admin_token):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        pin_resp = client.post('/api/auth/dispositivos/generar-pin',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Disp IR'})
        pin = pin_resp.get_json()['pin']
        client.post('/api/auth/dispositivos/enrolar',
            json={'codigo': pin, 'mac': 'DD:EE:FF:00:11:22', 'ip': '10.4.0.1'})

        resp = client.post('/api/facial/identificar-o-registrar',
            headers={'X-Device-MAC': 'DD:EE:FF:00:11:22'},
            json={'imagen': _b64_dummy_jpeg(), 'rut': '61.000.000-1', 'consentimiento': True})
        assert resp.status_code == 200
        assert resp.get_json()['registro_nuevo'] is True

    def test_identificar_o_registrar_persona_existente_sin_consentimiento_rechazado(self, client, admin_token):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'P IR SinCons', 'rut': '61.000.000-2'})

        resp = client.post('/api/facial/identificar-o-registrar', json={
            'imagen': _b64_dummy_jpeg(), 'rut': '61.000.000-2', 'consentimiento': False
        })
        assert resp.status_code == 403

    def test_identificar_o_registrar_deepface_no_detecta_rostro(self, client):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        with patch('deepface.DeepFace.represent', side_effect=ValueError('no face')):
            resp = client.post('/api/facial/identificar-o-registrar', json={
                'imagen': _b64_dummy_jpeg(), 'rut': '61.000.000-3'
            })
        assert resp.status_code == 400

    def test_identificar_o_registrar_db_error_interno(self, client):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None
        mock_cur.execute.side_effect = [None, Exception('DB error')]
        with patch('routes.facial.get_connection', return_value=mock_conn):
            resp = client.post('/api/facial/identificar-o-registrar', json={
                'imagen': _b64_dummy_jpeg(), 'rut': '61.000.000-4', 'consentimiento': True
            })
        assert resp.status_code == 500

    def test_identificar_o_registrar_excepcion_generica_externa(self, client):
        from routes.facial import _invalidar_cache
        _invalidar_cache()
        with patch('deepface.DeepFace.represent', side_effect=RuntimeError('modelo caido')):
            resp = client.post('/api/facial/identificar-o-registrar', json={
                'imagen': _b64_dummy_jpeg(), 'rut': '61.000.000-5'
            })
        assert resp.status_code == 500
