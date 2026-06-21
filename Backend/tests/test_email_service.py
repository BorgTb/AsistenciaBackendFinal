import os
from unittest.mock import MagicMock, patch

from services.email_service import _get_smtp_config, enviar_notificacion_marcacion


class TestEmailService:
    def test_get_smtp_config_lee_variables_entorno(self):
        with patch.dict(os.environ, {
            'SMTP_SERVER': 'mail.test.com',
            'SMTP_PORT': '465',
            'SMTP_USER': 'user@test.com',
            'SMTP_PASSWORD': 'secret',
            'SMTP_USE_TLS': 'false',
            'MAIL_FROM': 'from@test.com'
        }):
            cfg = _get_smtp_config()
            assert cfg['server'] == 'mail.test.com'
            assert cfg['port'] == 465
            assert cfg['user'] == 'user@test.com'
            assert cfg['password'] == 'secret'
            assert cfg['use_tls'] is False
            assert cfg['from_addr'] == 'from@test.com'

    def test_get_smtp_config_valores_default(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = _get_smtp_config()
            assert cfg['server'] == ''
            assert cfg['port'] == 587
            assert cfg['user'] == ''
            assert cfg['password'] == ''
            assert cfg['use_tls'] is True
            assert cfg['from_addr'] == ''

    def test_enviar_sin_email_retorna_temprano(self):
        assert enviar_notificacion_marcacion('', 'Juan', 'entrada', '2024-01-01') is None
        assert enviar_notificacion_marcacion(None, 'Juan', 'entrada', '2024-01-01') is None

    def test_enviar_sin_smtp_config(self):
        with patch.dict(os.environ, {
            'SMTP_SERVER': '', 'SMTP_USER': '', 'SMTP_PASSWORD': ''
        }), patch('services.email_service.logger') as mock_logger:
            enviar_notificacion_marcacion('juan@test.com', 'Juan', 'entrada', '2024-01-01')
            mock_logger.warning.assert_called_once()

    def test_enviar_notificacion_exito_con_tls(self):
        with patch.dict(os.environ, {
            'SMTP_SERVER': 'mail.test.com',
            'SMTP_PORT': '587',
            'SMTP_USER': 'user@test.com',
            'SMTP_PASSWORD': 'secret',
            'SMTP_USE_TLS': 'true',
            'MAIL_FROM': 'from@test.com',
        }), patch('smtplib.SMTP') as mock_smtp_class, \
           patch('services.email_service.logger') as mock_logger:
            mock_server = MagicMock()
            mock_smtp_class.return_value = mock_server

            enviar_notificacion_marcacion(
                'juan@test.com', 'Juan', 'entrada', '2024-01-01 10:00')

            mock_smtp_class.assert_called_once_with('mail.test.com', 587)
            mock_server.ehlo.assert_called()
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with('user@test.com', 'secret')
            mock_server.sendmail.assert_called_once()
            mock_server.quit.assert_called_once()
            mock_logger.info.assert_called_once()

    def test_enviar_notificacion_exito_sin_tls_ssl(self):
        with patch.dict(os.environ, {
            'SMTP_SERVER': 'mail.test.com',
            'SMTP_PORT': '465',
            'SMTP_USER': 'user@test.com',
            'SMTP_PASSWORD': 'secret',
            'SMTP_USE_TLS': 'false',
            'MAIL_FROM': 'from@test.com',
        }), patch('smtplib.SMTP_SSL') as mock_smtp_class:
            mock_server = MagicMock()
            mock_smtp_class.return_value = mock_server

            enviar_notificacion_marcacion(
                'juan@test.com', 'Juan', 'salida', '2024-01-01 18:00')

            mock_smtp_class.assert_called_once_with('mail.test.com', 465)
            mock_server.login.assert_called_once_with('user@test.com', 'secret')
            mock_server.sendmail.assert_called_once()
            mock_server.quit.assert_called_once()

    def test_enviar_notificacion_error_smtp(self):
        with patch.dict(os.environ, {
            'SMTP_SERVER': 'mail.test.com',
            'SMTP_PORT': '587',
            'SMTP_USER': 'user@test.com',
            'SMTP_PASSWORD': 'secret',
            'SMTP_USE_TLS': 'true',
            'MAIL_FROM': 'from@test.com',
        }), patch('smtplib.SMTP', side_effect=Exception('Connection refused')), \
           patch('services.email_service.logger') as mock_logger:
            enviar_notificacion_marcacion(
                'juan@test.com', 'Juan', 'entrada', '2024-01-01')
            mock_logger.error.assert_called_once()
