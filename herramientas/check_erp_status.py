import requests, json

BASE = 'http://localhost:5000'

r = requests.post(f'{BASE}/api/auth/login', json={'email': 'admin@empresa.cl', 'password': 'admin123'}, timeout=10)
token = r.json()['token']

r = requests.get(f'{BASE}/api/erp', headers={'Authorization': f'Bearer {token}'}, timeout=10)
erps = r.json()
for erp in erps:
    print(f'ERP: {erp["nombre"]} ({erp["tipo"]})')
    print(f'  URL: {erp["webhookUrl"]}')
    print(f'  Estado: {erp["ultimoEstado"]}')
    print(f'  Activo: {erp["activo"]}, Auto: {erp["envioAuto"]}')
    print()

if erps:
    eid = erps[0]['id']
    r = requests.get(f'{BASE}/api/erp/{eid}/estado', headers={'Authorization': f'Bearer {token}'}, timeout=10)
    print(f'Estado detallado: {json.dumps(r.json(), indent=2)}')
