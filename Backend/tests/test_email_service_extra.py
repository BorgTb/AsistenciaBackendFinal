from unittest.mock import patch, MagicMock


class TestEnviarCodigoSeguimiento:

    def test_sin_email_retorna_temprano(self):
        from services.email_service import enviar_codigo_seguimiento
        result = enviar_codigo_seguimiento(None, 'Test', 'COD-123')
        assert result is None

    def test_sin_smtp_config_retorna_temprano(self):
        from services.email_service import enviar_codigo_seguimiento
        with patch('services.email_service._get_smtp_config', return_value={'server': '', 'port': 587, 'user': '', 'password': '', 'use_tls': True, 'from_addr': ''}):
            result = enviar_codigo_seguimiento('test@test.cl', 'Test', 'COD-123')
            assert result is None

    def test_envio_exitoso(self):
        from services.email_service import enviar_codigo_seguimiento
        smtp_config = {
            'server': 'smtp.test.com', 'port': 587, 'user': 'user@test.com',
            'password': 'pass', 'use_tls': True, 'from_addr': 'noreply@test.com'
        }
        with patch('services.email_service._get_smtp_config', return_value=smtp_config), \
             patch('smtplib.SMTP') as mock_smtp_class:
            mock_instance = MagicMock()
            mock_smtp_class.return_value = mock_instance
            enviar_codigo_seguimiento('dest@test.cl', 'Juan', 'COD-999')
            assert mock_instance.starttls.called
            assert mock_instance.sendmail.called
            assert mock_instance.quit.called

    def test_envio_exitoso_sin_tls_ssl(self):
        from services.email_service import enviar_codigo_seguimiento
        smtp_config = {
            'server': 'smtp.test.com', 'port': 465, 'user': 'user@test.com',
            'password': 'pass', 'use_tls': False, 'from_addr': 'noreply@test.com'
        }
        with patch('services.email_service._get_smtp_config', return_value=smtp_config), \
             patch('smtplib.SMTP_SSL') as mock_smtp_class:
            mock_instance = MagicMock()
            mock_smtp_class.return_value = mock_instance
            enviar_codigo_seguimiento('dest@test.cl', 'Juan', 'COD-999')
            assert mock_instance.sendmail.called
            assert mock_instance.quit.called

    def test_error_smtp_loggeado(self):
        from services.email_service import enviar_codigo_seguimiento
        smtp_config = {
            'server': 'smtp.test.com', 'port': 587, 'user': 'user@test.com',
            'password': 'pass', 'use_tls': True, 'from_addr': 'noreply@test.com'
        }
        with patch('services.email_service._get_smtp_config', return_value=smtp_config), \
             patch('smtplib.SMTP', side_effect=Exception('SMTP error')):
            result = enviar_codigo_seguimiento('dest@test.cl', 'Juan', 'COD-999')
            assert result is None


class TestNotificarResolucionEliminacion:

    def test_sin_email_retorna_temprano(self):
        from services.email_service import notificar_resolucion_eliminacion
        result = notificar_resolucion_eliminacion(None, 'Test', 'aprobado', 'COD-123')
        assert result is None

    def test_sin_smtp_config_retorna_temprano(self):
        from services.email_service import notificar_resolucion_eliminacion
        with patch('services.email_service._get_smtp_config', return_value={'server': '', 'port': 587, 'user': '', 'password': '', 'use_tls': True, 'from_addr': ''}):
            result = notificar_resolucion_eliminacion('test@test.cl', 'Test', 'aprobado', 'COD-123')
            assert result is None

    def test_envio_aprobado(self):
        from services.email_service import notificar_resolucion_eliminacion
        smtp_config = {
            'server': 'smtp.test.com', 'port': 587, 'user': 'user@test.com',
            'password': 'pass', 'use_tls': True, 'from_addr': 'noreply@test.com'
        }
        with patch('services.email_service._get_smtp_config', return_value=smtp_config), \
             patch('smtplib.SMTP') as mock_smtp_class:
            mock_instance = MagicMock()
            mock_smtp_class.return_value = mock_instance
            notificar_resolucion_eliminacion('dest@test.cl', 'Ana', 'aprobado', 'COD-456')
            assert mock_instance.starttls.called
            assert mock_instance.sendmail.called

    def test_envio_rechazado(self):
        from services.email_service import notificar_resolucion_eliminacion
        smtp_config = {
            'server': 'smtp.test.com', 'port': 587, 'user': 'user@test.com',
            'password': 'pass', 'use_tls': True, 'from_addr': 'noreply@test.com'
        }
        with patch('services.email_service._get_smtp_config', return_value=smtp_config), \
             patch('smtplib.SMTP') as mock_smtp_class:
            mock_instance = MagicMock()
            mock_smtp_class.return_value = mock_instance
            notificar_resolucion_eliminacion('dest@test.cl', 'Luis', 'rechazado', 'COD-789')
            assert mock_instance.sendmail.called

    def test_error_smtp(self):
        from services.email_service import notificar_resolucion_eliminacion
        smtp_config = {
            'server': 'smtp.test.com', 'port': 587, 'user': 'user@test.com',
            'password': 'pass', 'use_tls': True, 'from_addr': 'noreply@test.com'
        }
        with patch('services.email_service._get_smtp_config', return_value=smtp_config), \
             patch('smtplib.SMTP', side_effect=Exception('SMTP fail')):
            result = notificar_resolucion_eliminacion('dest@test.cl', 'Luis', 'rechazado', 'COD-789')
            assert result is None
