import xmlrpc.client
import requests
import json
from datetime import datetime

UID = 2
PASS = 'admin123'
DB = 'odoo'
BASE = 'http://localhost:8069'

models = xmlrpc.client.ServerProxy(f'{BASE}/xmlrpc/2/object')

# 1. Create an employee
emp_id = models.execute_kw(DB, UID, PASS, 'hr.employee', 'create', [{
    'name': 'Juan Perez',
    'identification_id': '11.111.111-1',
}])
print(f'Empleado creado ID: {emp_id}')

# 2. Verify employee was created
emp = models.execute_kw(DB, UID, PASS, 'hr.employee', 'read', [emp_id, ['name', 'identification_id']])
print(f'Empleado: {emp}')

# 3. Test the webhook
TOKEN = 'sas-webhook-token-2026'
URL = f'{BASE}/asistencia/webhook'
payload = {
    'employee_id': '11.111.111-1',
    'check_type': 'entrada',
    'datetime': '2026-06-24T10:30:00',
}
headers = {'Authorization': f'Bearer {TOKEN}'}
r = requests.post(URL, json=payload, headers=headers, timeout=10)
resp = r.json()
print(f'\nWebhook response: {json.dumps(resp, indent=2)}')

if resp.get('result', {}).get('ok'):
    # 4. Check attendance was created
    att_ids = models.execute_kw(DB, UID, PASS, 'hr.attendance', 'search', [[('employee_id', '=', emp_id)]])
    if att_ids:
        att = models.execute_kw(DB, UID, PASS, 'hr.attendance', 'read', [att_ids, ['employee_id', 'check_in', 'check_out']])
        print(f'\nAsistencia en Odoo: {json.dumps(att, indent=2)}')
    else:
        print('\nNo se encontro asistencia en Odoo')
