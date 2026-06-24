{
    'name': 'Asistencia Webhook SAS',
    'version': '17.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Receptor webhook para sistema de asistencia SAS',
    'description': """
        Recibe webhooks desde el sistema SAS de asistencia
        y crea registros de hr.attendance automáticamente.
    """,
    'depends': ['hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
