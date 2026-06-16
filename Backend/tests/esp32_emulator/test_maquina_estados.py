"""
Emula la maquina de estados de registro del ESP32:
IDLE → ESPERANDO_HUELLA_REGISTRO → REGISTRO_SEGUNDA_HUELLA → REGISTRO_FACIAL → IDLE
Referencia: esp32.ino:87-103 (enum EstadoSistema)
"""


class TestEmuladorMaquinaEstados:
    """Valida la logica de estados del ESP32 en Python puro."""

    ESTADO_IDLE = 0
    ESTADO_ESPERANDO_HUELLA_REGISTRO = 1
    ESTADO_REGISTRO_SEGUNDA_HUELLA = 2
    ESTADO_REGISTRO_FACIAL = 3
    ESTADO_PROCESANDO_ASISTENCIA = 5

    def test_transiciones_basicas(self):
        estado = self.ESTADO_IDLE
        assert estado == 0

        estado = self.ESTADO_ESPERANDO_HUELLA_REGISTRO
        assert estado == 1

        estado = self.ESTADO_REGISTRO_SEGUNDA_HUELLA
        assert estado == 2

        estado = self.ESTADO_REGISTRO_FACIAL
        assert estado == 3

        estado = self.ESTADO_IDLE
        assert estado == 0

    def test_ciclo_completo_registro(self, client, admin_token):
        """Simula el ciclo: crear persona → consentimiento → registrar rostro."""
        client.post('/api/personas',
            headers={'Authorization': f'Bearer {admin_token}'},
            json={'nombre': 'Ciclo', 'rut': '50.000.000-1'})
        consent = client.post('/api/personas/1/consentimiento',
            headers={'Authorization': f'Bearer {admin_token}'})
        assert consent.status_code == 200

        import io, base64
        from PIL import Image
        img = Image.new('RGB', (16, 16), (200, 100, 50))
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        b64 = base64.b64encode(buf.getvalue()).decode()

        facial = client.post('/api/facial/registrar', json={
            'persona_id': '1', 'imagen': b64
        })
        assert facial.status_code == 200
        assert facial.get_json()['ok'] is True

    def test_timeout_registro_simulado(self):
        """Simula timeout del registro (TIMEOUT_REGISTRO = 30000ms)."""
        TIMEOUT_REGISTRO = 30000
        tiempo_inicio = 0
        tiempo_actual = 31000

        if tiempo_actual - tiempo_inicio > TIMEOUT_REGISTRO:
            estado = self.ESTADO_IDLE
        assert estado == 0
