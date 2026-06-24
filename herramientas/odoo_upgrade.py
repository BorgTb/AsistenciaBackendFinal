import xmlrpc.client

UID = 2
PASS = 'admin123'
DB = 'odoo'
BASE = 'http://localhost:8069'

models = xmlrpc.client.ServerProxy(f'{BASE}/xmlrpc/2/object')

# Find and upgrade our module
module_ids = models.execute_kw(DB, UID, PASS, 'ir.module.module', 'search', [[('name', '=', 'asistencia_webhook')]])
print(f'Module IDs: {module_ids}')

if module_ids:
    result = models.execute_kw(DB, UID, PASS, 'ir.module.module', 'button_immediate_upgrade', [module_ids])
    print(f'Upgrade result: {result}')
else:
    print('Module not found!')
