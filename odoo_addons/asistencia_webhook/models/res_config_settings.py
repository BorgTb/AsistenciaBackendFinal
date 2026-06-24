from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    asistencia_webhook_token = fields.Char(
        string='Token Webhook SAS',
        default='',
        help='Token de autenticacion para webhook del sistema SAS',
        config_parameter='asistencia_webhook.token',
    )
