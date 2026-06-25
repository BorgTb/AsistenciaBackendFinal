import xmlrpc.client
import psycopg2
import json
import os
import time
import sys
from datetime import datetime

# ─── Configuration ───────────────────────────────────────────────
ODOO_URL = os.getenv('ODOO_URL', 'http://localhost:8069')
ODOO_DB = os.getenv('ODOO_DB', 'odoo')
ODOO_USER = int(os.getenv('ODOO_USER', '2'))
ODOO_PASS = os.getenv('ODOO_PASS', 'admin')

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

def connect_odoo(url, db, uid, password):
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    return common, models

def install_module(models, db, uid, password, module_name):
    log('MODULE', f"Installing module '{module_name}'...")
    module_ids = models.execute_kw(db, uid, password, 'ir.module.module', 'search', [[('name', '=', module_name)]])
    if not module_ids:
        log('MODULE', f"Module '{module_name}' not found in addons path")
        return False
    models.execute_kw(db, uid, password, 'ir.module.module', 'button_immediate_install', [module_ids])
    log('MODULE', f"Module '{module_name}' installed")
    return True

def set_webhook_token(models, db, uid, password, token):
    log('TOKEN', f"Setting webhook token...")
    models.execute_kw(db, uid, password, 'ir.config_parameter', 'set_param', ['asistencia_webhook.token', token])
    log('TOKEN', 'Webhook token configured')

def get_sas_personas():
    log('SAS DB', 'Connecting to SAS database...')
    conn = psycopg2.connect(
        host=SAS_DB_HOST, port=SAS_DB_PORT,
        dbname=SAS_DB_NAME, user=SAS_DB_USER, password=SAS_DB_PASS
    )
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
        emp_id = models.execute_kw(db, uid, password, 'hr.employee', 'create', [{
            'name': nombre,
            'identification_id': rut_clean,
            'pin': rut_clean,
            'work_email': email or '',
            'notes': f'SAS persona_id={pid} | Empresa: {empresa}',
        }])
        log('ODOO EMPLOYEES', f"  Created {nombre} (RUT {rut_clean}) → employee ID {emp_id}")
        created += 1
    log('ODOO EMPLOYEES', f"Done: {created} created, {skipped} skipped")
    return created, skipped

def create_erp_integration():
    log('ERP INTEGRATION', 'Creating ERP integration in SAS database...')
    conn = psycopg2.connect(
        host=SAS_DB_HOST, port=SAS_DB_PORT,
        dbname=SAS_DB_NAME, user=SAS_DB_USER, password=SAS_DB_PASS
    )
    cur = conn.cursor()

    webhook_url = f"{ODOO_URL}/asistencia/webhook"
    headers = json.dumps({'Authorization': f'Bearer {WEBHOOK_TOKEN}'})
    field_map = json.dumps({'rut': 'employee_id', 'tipo': 'check_type', 'fecha_hora': 'datetime', 'nombre': 'employee_name'})

    cur.execute(
        "SELECT id FROM integraciones_erp WHERE nombre = %s AND webhook_url = %s",
        (ERP_NAME, webhook_url)
    )
    existing = cur.fetchone()
    if existing:
        log('ERP INTEGRATION', f"Integration '{ERP_NAME}' already exists (ID {existing[0]})")
        cur.close()
        conn.close()
        return existing[0]

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
    common, models = connect_odoo(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASS)

    # 2. Install custom module
    install_module(models, ODOO_DB, ODOO_USER, ODOO_PASS, 'asistencia_webhook')

    # 3. Set webhook token
    set_webhook_token(models, ODOO_DB, ODOO_USER, ODOO_PASS, WEBHOOK_TOKEN)

    # 4. Sync employees
    personas = get_sas_personas()
    sync_employees(models, ODOO_DB, ODOO_USER, ODOO_PASS, personas)

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
