import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


def _get_smtp_config():
    return {
        'server': os.getenv('SMTP_SERVER', ''),
        'port': int(os.getenv('SMTP_PORT', '587')),
        'user': os.getenv('SMTP_USER', ''),
        'password': os.getenv('SMTP_PASSWORD', ''),
        'use_tls': os.getenv('SMTP_USE_TLS', 'true').lower() == 'true',
        'from_addr': os.getenv('MAIL_FROM', os.getenv('SMTP_USER', '')),
    }


def enviar_notificacion_marcacion(persona_email, nombre, tipo, fecha_hora):
    if not persona_email:
        return

    config = _get_smtp_config()
    if not config['server'] or not config['user'] or not config['password']:
        logger.warning("SMTP no configurado. Revisa SMTP_SERVER, SMTP_USER, SMTP_PASSWORD en .env")
        return

    try:
        tipo_label = 'Entrada' if tipo == 'entrada' else 'Salida'
        fecha_str = str(fecha_hora)

        msg = MIMEMultipart('alternative')
        msg['From'] = config['from_addr']
        msg['To'] = persona_email
        msg['Subject'] = f"Notificación de Marcación - {nombre}"

        text = f"""Hola {nombre},

Se ha registrado tu marcación de tipo {tipo_label} el {fecha_str}.

Saludos,
Sistema de Asistencia"""

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2>Notificación de Marcación</h2>
    <table style="border-collapse: collapse; margin: 15px 0;">
        <tr><td style="padding: 8px 12px; font-weight: bold;">Nombre:</td><td style="padding: 8px 12px;">{nombre}</td></tr>
        <tr><td style="padding: 8px 12px; font-weight: bold;">Tipo:</td><td style="padding: 8px 12px;">{tipo_label}</td></tr>
        <tr><td style="padding: 8px 12px; font-weight: bold;">Fecha y Hora:</td><td style="padding: 8px 12px;">{fecha_str}</td></tr>
    </table>
    <hr>
    <p style="color: #666; font-size: 12px;">Sistema de Asistencia</p>
</body>
</html>"""

        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))

        if config['use_tls']:
            server = smtplib.SMTP(config['server'], config['port'])
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(config['server'], config['port'])

        server.login(config['user'], config['password'])
        server.sendmail(config['from_addr'], [persona_email], msg.as_string())
        server.quit()

        logger.info(f"Correo enviado a {persona_email} para marcación de {nombre} ({tipo})")
    except Exception as e:
        logger.error(f"Error al enviar correo a {persona_email}: {e}")
