import requests, re, json

session = requests.Session()
BASE = 'http://localhost:8069'

r1 = session.get(f'{BASE}/web/login', timeout=10)
match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', r1.text)
csrf = match.group(1) if match else ''
print(f'CSRF: {csrf[:30] if csrf else "none"}')

r2 = session.post(f'{BASE}/web/login', data={
    'login': 'anmeza6268@gmail.com',
    'password': 'admin123',
    'csrf_token': csrf,
}, allow_redirects=False, timeout=10)
print(f'Login status: {r2.status_code}')
print(f'Location: {r2.headers.get("Location")}')
print(f'Session cookie: {session.cookies.get("session_id", "none")[:30]}')

if r2.status_code in (302, 303):
    dest = r2.headers.get('Location', '/web')
    r3 = session.get(f'{BASE}{dest}', timeout=10)
    print(f'Final: {r3.url} ({r3.status_code})')
    print(f'Logged in: {"my_odoo_server" in r3.text or "session_info" in r3.text}')

# Try JSON-RPC install
session_id = session.cookies.get('session_id')
if session_id:
    r4 = session.post(f'{BASE}/web/dataset/call_kw', json={
        'jsonrpc': '2.0',
        'method': 'call',
        'params': {
            'model': 'ir.module.module',
            'method': 'search_read',
            'args': [[['name', '=', 'asistencia_webhook']]],
            'kwargs': {'fields': ['id', 'name', 'state']},
        },
        'id': 1,
    }, timeout=10)
    print(f'\nModule search: {json.dumps(r4.json(), indent=2)[:300]}')

print('\nDBG - Session cookie:', session.cookies.get('session_id'))
