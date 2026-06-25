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


def enviar_codigo_seguimiento(email_destino, nombre, codigo_seguimiento):
    if not email_destino:
        return

    config = _get_smtp_config()
    if not config['server'] or not config['user'] or not config['password']:
        logger.warning("SMTP no configurado. No se pudo enviar el código de seguimiento.")
        return

    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = config['from_addr']
        msg['To'] = email_destino
        msg['Subject'] = "Solicitud de eliminación de datos - Código de seguimiento"

        text = f"""Hola {nombre},

Hemos recibido tu solicitud de eliminación de datos biométricos y personales.

Tu código de seguimiento es: {codigo_seguimiento}

Puedes usarlo para consultar el estado de tu solicitud en cualquier momento.

Saludos,
Sistema de Asistencia"""

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; padding: 20px; max-width: 600px; margin: 0 auto;">
    <h2>Solicitud de eliminación de datos</h2>
    <p>Hola <strong>{nombre}</strong>,</p>
    <p>Hemos recibido tu solicitud de eliminación de datos biométricos y personales.</p>
    <div style="background: #f0f4f8; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0;">
        <p style="color: #64748b; font-size: 14px; margin: 0 0 8px;">Tu código de seguimiento es:</p>
        <p style="font-family: monospace; font-size: 28px; font-weight: 700; letter-spacing: 6px; color: #1d4ed8; margin: 0;">{codigo_seguimiento}</p>
    </div>
    <p>Puedes usarlo para consultar el estado de tu solicitud en cualquier momento.</p>
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
        server.sendmail(config['from_addr'], [email_destino], msg.as_string())
        server.quit()

        logger.info(f"Código de seguimiento enviado a {email_destino}")
    except Exception as e:
        logger.error(f"Error al enviar código de seguimiento a {email_destino}: {e}")


def notificar_resolucion_eliminacion(email_destino, nombre, estado, codigo_seguimiento):
    if not email_destino:
        return

    config = _get_smtp_config()
    if not config['server'] or not config['user'] or not config['password']:
        logger.warning("SMTP no configurado. No se pudo notificar la resolución.")
        return

    try:
        if estado == 'aprobada':
            asunto = "Solicitud de eliminación de datos aprobada"
            texto_intro = "Tu solicitud de eliminación de datos ha sido aprobada."
            detalle = (
                "Tu RUT, datos faciales y huella dactilar han sido eliminados del sistema. "
                "Tus registros de asistencia se mantienen intactos."
            )
            color = "#16a34a"
        else:
            asunto = "Solicitud de eliminación de datos rechazada"
            texto_intro = "Tu solicitud de eliminación de datos ha sido rechazada."
            detalle = (
                "Ninguno de tus datos ha sido modificado. "
                "Si tienes dudas, contacta al administrador del sistema para más información."
            )
            color = "#dc2626"

        msg = MIMEMultipart('alternative')
        msg['From'] = config['from_addr']
        msg['To'] = email_destino
        msg['Subject'] = asunto

        text = f"""Hola {nombre},

{texto_intro}

{detalle}

Código de solicitud: {codigo_seguimiento}

Saludos,
Sistema de Asistencia"""

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; padding: 20px; max-width: 600px; margin: 0 auto;">
    <h2 style="color: {color};">{texto_intro}</h2>
    <p>Hola <strong>{nombre}</strong>,</p>
    <p>{detalle}</p>
    <div style="background: #f8fafc; border-radius: 12px; padding: 16px; margin: 20px 0;">
        <p style="color: #64748b; font-size: 14px; margin: 0;">Código de solicitud:</p>
        <p style="font-family: monospace; font-size: 18px; font-weight: 600; color: #1d4ed8; margin: 4px 0 0;">{codigo_seguimiento}</p>
    </div>
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
        server.sendmail(config['from_addr'], [email_destino], msg.as_string())
        server.quit()

        logger.info(f"Resolución de eliminación notificada a {email_destino}: {estado}")
    except Exception as e:
        logger.error(f"Error al notificar resolución a {email_destino}: {e}")
