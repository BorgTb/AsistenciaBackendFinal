import json
import logging
from datetime import datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AsistenciaWebhookController(http.Controller):

    @http.route('/asistencia/webhook', type='json', auth='none', methods=['POST'], csrf=False)
    def webhook_recibir(self):
        headers = request.httprequest.headers
        data = request.get_json_data()

        if not data:
            return {'ok': False, 'error': 'Payload JSON requerido'}

        token = headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return {'ok': False, 'error': 'Token de autenticacion requerido'}

        env = request.env(su=True)

        config = env['ir.config_parameter'].sudo()
        expected_token = config.get_param('asistencia_webhook.token', '')
        if not expected_token:
            _logger.warning('Webhook token not configured. Set asistencia_webhook.token in System Parameters')
            return {'ok': False, 'error': 'Webhook no configurado en Odoo'}

        if token != expected_token:
            return {'ok': False, 'error': 'Token invalido'}

        employee_id = data.get('employee_id')
        check_type = data.get('check_type', 'entrada')
        datetime_str = data.get('datetime')

        if not employee_id or not datetime_str:
            return {'ok': False, 'error': 'Faltan campos requeridos: employee_id, datetime'}

        if not datetime_str.endswith('Z') and '+' not in datetime_str:
            datetime_str += 'Z'

        try:
            dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00')).replace(tzinfo=None)
        except Exception as e:
            return {'ok': False, 'error': f'Formato de datetime invalido: {e}'}

        employee = env['hr.employee'].sudo().search([
            ('identification_id', '=', employee_id),
            ('active', '=', True),
        ], limit=1)

        if not employee:
            employee = env['hr.employee'].sudo().search([
                ('pin', '=', employee_id),
                ('active', '=', True),
            ], limit=1)

        if not employee:
            return {'ok': False, 'error': f'Empleado no encontrado con identification_id={employee_id}'}

        try:
            if check_type in ('entrada', 'in', 'check_in'):
                open_att = env['hr.attendance'].sudo().search([
                    ('employee_id', '=', employee.id),
                    ('check_out', '=', False),
                ], limit=1)
                if open_att:
                    return {
                        'ok': False,
                        'error': f'El empleado {employee.name} ya tiene una entrada abierta a las {open_att.check_in}',
                    }

                attendance = env['hr.attendance'].sudo().create({
                    'employee_id': employee.id,
                    'check_in': dt,
                })
                _logger.info('Entrada creada: employee=%s, datetime=%s', employee.name, dt)

                return {
                    'ok': True,
                    'attendance_id': attendance.id,
                    'employee': employee.name,
                    'check_type': 'entrada',
                    'datetime': dt.isoformat(),
                }

            elif check_type in ('salida', 'out', 'check_out'):
                open_att = env['hr.attendance'].sudo().search([
                    ('employee_id', '=', employee.id),
                    ('check_out', '=', False),
                ], limit=1)

                if not open_att:
                    return {
                        'ok': False,
                        'error': f'No hay entrada abierta para {employee.name}',
                    }

                open_att.write({'check_out': dt})
                _logger.info('Salida registrada: employee=%s, check_in=%s, check_out=%s',
                             employee.name, open_att.check_in, dt)

                return {
                    'ok': True,
                    'attendance_id': open_att.id,
                    'employee': employee.name,
                    'check_type': 'salida',
                    'check_in': open_att.check_in.isoformat() if open_att.check_in else None,
                    'check_out': dt.isoformat(),
                }

            else:
                return {'ok': False, 'error': f'Tipo de marcacion invalido: {check_type}'}

        except Exception as e:
            _logger.error('Error creando asistencia: %s', e)
            return {'ok': False, 'error': str(e)}
