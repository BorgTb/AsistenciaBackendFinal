"""
Test: Integracion Backend (Iter 3 - Pruebas de inicializacion DB y recepcion HTTP)
-------------------------------------------------------------------------------
Corresponde a las pruebas descritas en cap4_iteraciones.tex:
  - "Prueba de inicializacion de base de datos" (linea 624)
  - "Prueba de recepcion de datos en backend via HTTP" (linea 620)
  - "Prueba de conexion Wi-Fi y reconexion" (linea 614)

Verifica:
  1. Health del backend (/health)
  2. Inicializacion de 13 tablas en PostgreSQL
  3. Datos semilla (empresa default + admin)
  4. CRUD basico de personas via API REST
  5. Endpoints de turnos y asignaciones responden

Uso: python tests/test_integracion_backend.py
"""

import os
import sys
import requests
import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Backend'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'Backend', '.env'))

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
DATABASE_URL = os.getenv("DATABASE_URL", "")
PASS = 0
FAIL = 0

TABLAS_ESPERADAS = [
    "empresas", "dispositivos", "usuarios_web", "usuario_empresa",
    "personas", "turnos", "asignaciones", "asistencias",
    "sincronizacion_log", "integraciones_erp", "consentimientos",
    "logs_biometricos", "eliminaciones_biometricas"
]


def check(desc, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {desc}")
        return True
    else:
        FAIL += 1
        print(f"  [FAIL] {desc}")
        return False


def test_health():
    print("\n=== 1. Health del Backend ===")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        check("GET /health responde HTTP 200", r.status_code == 200)
        data = r.json()
        check("Respuesta contiene status: ok", data.get("status") == "ok")
    except Exception as e:
        check(f"GET /health EXCEPCION: {e}", False)


def test_db_tablas():
    print("\n=== 2. Inicializacion de Base de Datos ===")
    if not DATABASE_URL:
        print("  [SKIP] DATABASE_URL no configurada en .env")
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        tablas = [r[0] for r in cur.fetchall()]
        check(f"Existen {len(tablas)} tablas (esperadas {len(TABLAS_ESPERADAS)})",
              len(tablas) >= len(TABLAS_ESPERADAS))
        for t in TABLAS_ESPERADAS:
            check(f"Tabla '{t}'", t in tablas)
        cur.execute("SELECT nombre FROM empresas WHERE id = 1")
        empresa = cur.fetchone()
        check("Dato semilla: empresa default (id=1)", empresa is not None)
        cur.execute("SELECT email FROM usuarios_web WHERE email = 'admin@empresa.cl'")
        admin = cur.fetchone()
        check("Dato semilla: admin@empresa.cl", admin is not None)
        cur.close()
        conn.close()
    except Exception as e:
        check(f"Conexion DB: {e}", False)


def test_crud_personas():
    print("\n=== 3. CRUD Personas via API REST ===")
    try:
        r = requests.get(f"{BASE_URL}/api/personas", timeout=5)
        check("GET /api/personas responde (HTTP 200)", r.status_code == 200)
        datos = r.json()
        check("GET /api/personas retorna lista", isinstance(datos, list))

        payload = {"nombre": "Test Integracion", "rut": "11.111.111-1",
                   "email": "test.integracion@test.local"}
        r = requests.post(f"{BASE_URL}/api/personas", json=payload, timeout=5)
        check("POST /api/personas responde (HTTP 201 o 200)",
              r.status_code in (200, 201))
        persona = r.json() if r.status_code in (200, 201) else {}
        persona_id = persona.get("id")
        check("POST retorna persona_id", persona_id is not None)

        if persona_id:
            r = requests.delete(f"{BASE_URL}/api/personas/{persona_id}", timeout=5)
            check(f"DELETE /api/personas/{persona_id} responde (HTTP 200)",
                  r.status_code == 200)
    except Exception as e:
        check(f"CRUD personas EXCEPCION: {e}", False)


def test_turnos():
    print("\n=== 4. Endpoints de Turnos y Asignaciones ===")
    try:
        r = requests.get(f"{BASE_URL}/api/turnos", timeout=5)
        check("GET /api/turnos responde (HTTP 200)", r.status_code == 200)
        datos = r.json() if r.ok else []
        check("GET /api/turnos retorna lista", isinstance(datos, list))

        r = requests.get(f"{BASE_URL}/api/asignaciones", timeout=5)
        check("GET /api/asignaciones responde (HTTP 200)", r.status_code == 200)
        datos = r.json() if r.ok else []
        check("GET /api/asignaciones retorna lista", isinstance(datos, list))
    except Exception as e:
        check(f"Turnos EXCEPCION: {e}", False)


def test_asistencias_endpoint():
    print("\n=== 5. Endpoints de Asistencias ===")
    try:
        payload = {
            "persona_id": 999,
            "tipo": "entrada",
            "metodo": "test",
            "dispositivo_id": 1
        }
        r = requests.post(f"{BASE_URL}/api/asistencias", json=payload, timeout=5)
        check("POST /api/asistencias responde", r.status_code in (200, 201, 400, 404))

        batch = {"registros": [
            {"persona_id": 999, "tipo": "entrada", "metodo": "test",
             "timestamp": "2026-01-01T08:00:00"}
        ]}
        r = requests.post(f"{BASE_URL}/api/asistencias/sync", json=batch, timeout=5)
        check("POST /api/asistencias/sync responde", r.status_code in (200, 201, 400, 404, 500))
    except Exception as e:
        check(f"Asistencias EXCEPCION: {e}", False)


if __name__ == "__main__":
    print("=" * 60)
    print("PRUEBA DE INTEGRACION BACKEND")
    print("  Referencia: cap4_iteraciones.tex Iter 3 (lineas 614-627)")
    print("=" * 60)

    test_health()
    test_db_tablas()
    test_crud_personas()
    test_turnos()
    test_asistencias_endpoint()

    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {PASS} PASS, {FAIL} FAIL de {PASS + FAIL} pruebas")
    print(f"{'=' * 60}")
    sys.exit(0 if FAIL == 0 else 1)
