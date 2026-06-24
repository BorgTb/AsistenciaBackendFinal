import xmlrpc.client

UID = 2
PASS = 'admin123'
DB = 'odoo'
BASE = 'http://localhost:8069'

models = xmlrpc.client.ServerProxy(f'{BASE}/xmlrpc/2/object')

print('Updating module list...')
result = models.execute_kw(DB, UID, PASS, 'ir.module.module', 'update_list', [])
print(f'Update list result type: {type(result).__name__}')

module_ids = models.execute_kw(DB, UID, PASS, 'ir.module.module', 'search', [[('name', '=', 'asistencia_webhook')]])
print(f'Module IDs: {module_ids}')

if module_ids:
    result = models.execute_kw(DB, UID, PASS, 'ir.module.module', 'button_immediate_install', [module_ids])
    print(f'Install result: {result}')

    models.execute_kw(DB, UID, PASS, 'ir.config_parameter', 'set_param', ['asistencia_webhook.token', 'sas-webhook-token-2026'])
    print('Webhook token configured: sas-webhook-token-2026')
else:
    print('Module not found')
    all_mods = models.execute_kw(DB, UID, PASS, 'ir.module.module', 'search_read', [[], ['name', 'state']])
    asist_mods = [m for m in all_mods if 'hook' in m['name'] or 'asist' in m['name']]
    print(f'Related: {asist_mods[:10]}')
    # Check a few modules to see naming pattern
    test = models.execute_kw(DB, UID, PASS, 'ir.module.module', 'search_read', [[], ['name', 'state']], {'limit': 5})
    print(f'Sample: {test}')
