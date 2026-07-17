import xmlrpc.client
import psycopg2
import json
import os
import re
import time
import sys
from datetime import datetime
from urllib.parse import urlparse

# La consola de Windows usa cp1252 y no puede encodear el banner ni los guiones
# largos de los logs; sin esto el script muere al final con UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ─── Read env from Backend/.env ──────────────────────────────────
_env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Backend', '.env')
if os.path.exists(_env_file):
    with open(_env_file, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))

# ─── Configuration ───────────────────────────────────────────────
ODOO_URL = os.getenv('ODOO_URL', 'http://localhost:8069')
ODOO_DB = os.getenv('ODOO_DB', 'odoo')
ODOO_USER = os.getenv('ODOO_USER', 'admin')
ODOO_PASS = os.getenv('ODOO_PASS', 'admin')

DATABASE_URL = os.getenv('DATABASE_URL', '')
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    SAS_DB_HOST = parsed.hostname or 'localhost'
    SAS_DB_PORT = parsed.port or 5432
    SAS_DB_USER = parsed.username or 'sas'
    SAS_DB_PASS = parsed.password or 'sas123'
    SAS_DB_NAME = parsed.path.lstrip('/') if parsed.path else 'sas_db'
else:
    SAS_DB_HOST = os.getenv('SAS_DB_HOST', 'localhost')
    SAS_DB_PORT = int(os.getenv('SAS_DB_PORT', '5432'))
    SAS_DB_NAME = os.getenv('SAS_DB_NAME', 'sas_db')
    SAS_DB_USER = os.getenv('SAS_DB_USER', 'sas')
    SAS_DB_PASS = os.getenv('SAS_DB_PASS', 'sas123')

WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN', 'sas-webhook-token-2026')
ERP_NAME = os.getenv('ERP_NAME', 'Odoo Test ERP')

# ─── Helpers ─────────────────────────────────────────────────────
def log(step, msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{step}] {msg}", flush=True)

def wait_for_odoo(url, timeout=120):
    log('ODOO', 'Waiting for Odoo to be ready...')
    start = time.time()
    while time.time() - start < timeout:
        try:
            common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
            version = common.version()
            log('ODOO', f"Odoo {version.get('server_version', '?')} ready")
            return common
        except Exception as e:
            sys.stdout.write('.')
            sys.stdout.flush()
            time.sleep(3)
    raise TimeoutError('Odoo did not become ready')

def connect_odoo(url, db, username, password):
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    if not uid:
        raise SystemExit(
            f"Odoo rejected the credentials for user '{username}' on database '{db}'.\n"
            f"Check ODOO_USER / ODOO_PASS / ODOO_DB (the compose file creates db 'odoo' with admin/admin)."
        )
    log('ODOO', f"Authenticated as '{username}' (uid {uid})")
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    return common, models, uid

def install_module(models, db, uid, password, module_name):
    log('MODULE', f"Installing module '{module_name}'...")
    module_ids = models.execute_kw(db, uid, password, 'ir.module.module', 'search', [[('name', '=', module_name)]])
    if not module_ids:
        log('MODULE', f"Module '{module_name}' not found in addons path")
        return False
    models.execute_kw(db, uid, password, 'ir.module.module', 'button_immediate_install', [module_ids])
    log('MODULE', f"Module '{module_name}' installed")
    return True

REQUIRED_GROUPS = [
    # identification_id y pin de hr.employee solo son legibles con este grupo:
    # sin el, hasta admin recibe Fault 4 al leerlos.
    ('hr', 'group_hr_user'),
    # Por defecto admin queda con group_hr_attendance_own_reader y solo ve sus
    # propias marcaciones: la UI y el XML-RPC muestran cero asistencias aunque
    # el webhook las haya creado correctamente.
    ('hr_attendance', 'group_hr_attendance_manager'),
]

def grant_odoo_groups(models, db, uid, password):
    """Da al usuario los grupos necesarios para leer empleados y asistencias.

    El webhook no los necesita porque corre con sudo(), pero setup.py y la UI si.
    Ojo: el compose arranca Odoo con --init=base, que reescribe los grupos de
    admin desde el XML de base en cada reinicio y revierte esto.
    """
    log('GROUPS', 'Ensuring HR access...')
    for module, name in REQUIRED_GROUPS:
        ref = models.execute_kw(db, uid, password, 'ir.model.data', 'search_read',
                                [[('module', '=', module), ('name', '=', name)]],
                                {'fields': ['res_id'], 'limit': 1})
        if not ref:
            log('GROUPS', f"  group {module}.{name} not found; is the module installed?")
            continue
        models.execute_kw(db, uid, password, 'res.users', 'write',
                          [[uid], {'groups_id': [(4, ref[0]['res_id'])]}])
        log('GROUPS', f"  granted {module}.{name}")
    return True

def set_webhook_token(models, db, uid, password, token):
    log('TOKEN', f"Setting webhook token...")
    models.execute_kw(db, uid, password, 'ir.config_parameter', 'set_param', ['asistencia_webhook.token', token])
    log('TOKEN', 'Webhook token configured')

def _sas_connect():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=SAS_DB_HOST, port=SAS_DB_PORT,
        dbname=SAS_DB_NAME, user=SAS_DB_USER, password=SAS_DB_PASS
    )

def get_sas_personas():
    log('SAS DB', 'Connecting to SAS database...')
    conn = _sas_connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, p.nombre, p.rut, p.email, COALESCE(e.nombre, 'Sin empresa') as empresa
        FROM personas p
        LEFT JOIN empresas e ON e.id = p.empresa_id
        WHERE p.activo = TRUE
        ORDER BY p.id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    log('SAS DB', f"Found {len(rows)} active personas")
    return rows

def sync_employees(models, db, uid, password, personas):
    log('ODOO EMPLOYEES', f"Creating {len(personas)} employees in Odoo...")
    created = 0
    skipped = 0
    for pid, nombre, rut, email, empresa in personas:
        rut_clean = rut.strip() if rut else f"NO-RUT-{pid}"
        existing = models.execute_kw(db, uid, password, 'hr.employee', 'search', [
            ['|', ('identification_id', '=', rut_clean), ('pin', '=', rut_clean)]
        ])
        if existing:
            log('ODOO EMPLOYEES', f"  Skipped {nombre} (RUT {rut_clean}) — already exists")
            skipped += 1
            continue
        digits_only = re.sub(r'[^0-9]', '', rut_clean)
        pin = digits_only[-8:] if len(digits_only) >= 8 else digits_only.zfill(8)
        emp_id = models.execute_kw(db, uid, password, 'hr.employee', 'create', [{
            'name': nombre,
            'identification_id': rut_clean,
            'pin': pin,
            'work_email': email or '',
            'notes': f'SAS persona_id={pid} | Empresa: {empresa}',
        }])
        log('ODOO EMPLOYEES', f"  Created {nombre} (RUT {rut_clean}) → employee ID {emp_id}")
        created += 1
    log('ODOO EMPLOYEES', f"Done: {created} created, {skipped} skipped")
    return created, skipped

def create_erp_integration():
    log('ERP INTEGRATION', 'Creating ERP integration in SAS database...')
    conn = _sas_connect()
    cur = conn.cursor()

    odoo_internal = os.getenv('ODOO_INTERNAL_URL', 'http://localhost:8069')
    webhook_url = f"{odoo_internal}/asistencia/webhook"
    headers = json.dumps({'Authorization': f'Bearer {WEBHOOK_TOKEN}'})
    field_map = json.dumps({'rut': 'employee_id', 'tipo': 'check_type', 'fecha_hora': 'datetime', 'nombre': 'employee_name'})

    cur.execute(
        "SELECT id FROM integraciones_erp WHERE nombre = %s AND webhook_url = %s",
        (ERP_NAME, webhook_url)
    )
    existing = cur.fetchone()
    if existing:
        erp_id = existing[0]
        cur.execute(
            "UPDATE integraciones_erp SET webhook_url = %s, headers = %s, field_map = %s WHERE id = %s",
            (webhook_url, headers, field_map, erp_id)
        )
        conn.commit()
        log('ERP INTEGRATION', f"Integration '{ERP_NAME}' updated (ID {erp_id})")
        cur.close()
        conn.close()
        return erp_id

    cur.execute(
        """INSERT INTO integraciones_erp (empresa_id, nombre, tipo, webhook_url, headers, field_map, envio_auto, activo)
           VALUES (1, %s, 'odoo', %s, %s, %s, TRUE, TRUE) RETURNING id""",
        (ERP_NAME, webhook_url, headers, field_map)
    )
    erp_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    log('ERP INTEGRATION', f"Integration '{ERP_NAME}' created with ID {erp_id}")
    return erp_id


# ─── Main ────────────────────────────────────────────────────────
def main():
    log('START', '=== Odoo Test Environment Setup ===')

    # 1. Wait for Odoo
    wait_for_odoo(ODOO_URL)
    common, models, uid = connect_odoo(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASS)

    # 2. Install custom module
    install_module(models, ODOO_DB, uid, ODOO_PASS, 'asistencia_webhook')

    # 3. Set webhook token
    set_webhook_token(models, ODOO_DB, uid, ODOO_PASS, WEBHOOK_TOKEN)

    # 3b. Sin estos grupos no se leen identification_id/pin ni las asistencias ajenas
    grant_odoo_groups(models, ODOO_DB, uid, ODOO_PASS)

    # 4. Sync employees
    personas = get_sas_personas()
    sync_employees(models, ODOO_DB, uid, ODOO_PASS, personas)

    # 5. Create ERP integration in SAS
    erp_id = create_erp_integration()

    log('DONE', f"""
    ╔══════════════════════════════════════════════════════════╗
    ║                   SETUP COMPLETE                        ║
    ╠══════════════════════════════════════════════════════════╣
    ║  Odoo       : {ODOO_URL:<41} ║
    ║  Database   : {ODOO_DB:<41} ║
    ║  ERP name   : {ERP_NAME:<41} ║
    ║  ERP ID     : {erp_id:<41} ║
    ║  Token      : {WEBHOOK_TOKEN:<41} ║
    ║  Webhook    : {ODOO_URL}/asistencia/webhook ║
    ╚══════════════════════════════════════════════════════════╝

    Next steps:
      1. Access Odoo at {ODOO_URL}  (user: admin, password: admin)
      2. Create an attendance via SAS → it will auto-push to Odoo
      3. Check Odoo > Employees > Attendances for the records
    """)


if __name__ == '__main__':
    main()
