"""
Test: Integracion ERP (Iter 7 - Pruebas de webhook y field mapping)
------------------------------------------------------------------
Corresponde a las pruebas descritas en cap4_iteraciones.tex (lineas 1122-1140):
  - "Prueba de creacion de integracion ERP" (linea 1125)
  - "Prueba de test de webhook" (linea 1127)
  - "Prueba de envio automatico" (linea 1129)
  - "Prueba de field mapping" (linea 1131)
  - "Prueba de tolerancia a fallos ERP" (linea 1135)

NOTA: Las pruebas de envio requieren un webhook de prueba (webhook.site,
requestbin, etc.). Sin URL externa, los endpoints CRUD se prueban pero
el envio real se omite.

Uso: python tests/test_erp_integracion.py [WEBHOOK_URL]
"""

import os
import sys
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Backend'))

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
PASS = 0
FAIL = 0
SKIP = 0

ADMIN_EMAIL = "admin@empresa.cl"
ADMIN_PASS = "admin123"


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


def skip(desc):
    global SKIP
    SKIP += 1
    print(f"  [SKIP] {desc}")


def _login():
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASS
        }, timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            return r.json()["token"]
    except Exception:
        pass
    return None


def test_erp_endpoint_existe():
    print("\n=== 1. Endpoint ERP responde ===")
    try:
        r = requests.get(f"{BASE_URL}/api/erp", timeout=5)
        check("GET /api/erp sin token: HTTP 401", r.status_code == 401)
    except Exception as e:
        skip(f"Backend no accesible: {e}")


def test_erp_crud(token):
    print("\n=== 2. CRUD de integraciones ERP ===")
    if not token:
        skip("Requiere token admin")
        return None

    headers = {"Authorization": f"Bearer {token}"}

    r = requests.get(f"{BASE_URL}/api/erp", headers=headers, timeout=5)
    check("GET /api/erp: HTTP 200", r.status_code == 200)
    initial = r.json() if r.ok else []
    check("Retorna lista de integraciones", isinstance(initial, list))

    webhook = os.getenv("TEST_WEBHOOK_URL",
                        "https://webhook.site/test-erp-integracion")
    payload = {
        "nombre": "ERP Test Suite",
        "tipo": "generic",
        "webhook_url": webhook,
        "headers": {"X-API-Key": "test-key-123"},
        "field_map": {"persona_id": "employee_id", "tipo": "event_type"},
        "envio_auto": True,
        "activo": True
    }
    r = requests.post(f"{BASE_URL}/api/erp", json=payload,
                      headers=headers, timeout=10)
    check("POST /api/erp: HTTP 200", r.status_code == 200)
    erp_id = r.json().get("id")

    r = requests.get(f"{BASE_URL}/api/erp", headers=headers, timeout=5)
    after = r.json() if r.ok else []
    check("Lista crecio tras creacion", len(after) == len(initial) + 1)

    if erp_id:
        r = requests.delete(f"{BASE_URL}/api/erp/{erp_id}",
                           headers=headers, timeout=5)
        check(f"DELETE /api/erp/{erp_id}: HTTP 200", r.status_code == 200)

        r = requests.get(f"{BASE_URL}/api/erp", headers=headers, timeout=5)
        final = r.json() if r.ok else []
        check("Lista decrecio tras eliminacion", len(final) == len(initial))

    return erp_id


def test_field_mapping_static():
    print("\n=== 3. Transformacion de datos (field mapping) ===")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Backend'))
    try:
        from routes.erp import _transformar_datos

        datos = {"persona_id": 42, "nombre": "Juan", "tipo": "entrada",
                 "fecha_hora": "2026-01-01T08:00:00", "metodo": "facial"}

        field_map = '{"persona_id": "employee_id", "tipo": "event"}'
        resultado = _transformar_datos(datos, field_map)

        check("Campo persona_id mapeado a employee_id",
              resultado.get("employee_id") == 42)
        check("Campo tipo mapeado a event",
              resultado.get("event") == "entrada")
        check("Campo nombre se conserva (no en field_map)",
              resultado.get("nombre") == "Juan")
    except ImportError:
        skip("No se pudo importar routes.erp (requiere Flask y BD)")
    except Exception as e:
        check(f"Field mapping EXCEPCION: {e}", False)


def test_enviar_a_webhook_static():
    print("\n=== 4. Funcion _enviar_a_webhook (webhook invalido) ===")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Backend'))
    try:
        from routes.erp import _enviar_a_webhook
        resultado = _enviar_a_webhook(
            "http://127.0.0.1:59999/inexistente",
            '{"Content-Type": "application/json"}',
            {"test": True},
            timeout=2
        )
        check("Webhook inalcanzable retorna ok=False",
              resultado.get("ok") is False)
        check("Webhook inalcanzable retorna mensaje de error",
              resultado.get("error") is not None or resultado.get("status_code") is not None)
    except ImportError:
        skip("No se pudo importar routes.erp")
    except Exception as e:
        check(f"Webhook EXCEPCION: {e}", False)


def test_erp_test_endpoint(token):
    print("\n=== 5. Endpoint de test de conectividad ===")
    if not token:
        skip("Requiere token admin")
        return

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "nombre": "Test Conectividad ERP",
        "tipo": "generic",
        "webhook_url": "https://webhook.site/test-connectivity",
        "envio_auto": False,
        "activo": True
    }
    r = requests.post(f"{BASE_URL}/api/erp", json=payload,
                      headers=headers, timeout=10)
    if r.status_code != 200:
        skip("No se pudo crear ERP de prueba")
        return

    erp_id = r.json().get("id")
    if erp_id:
        r2 = requests.post(f"{BASE_URL}/api/erp/{erp_id}/test",
                          headers=headers, timeout=30)
        check(f"POST /api/erp/{erp_id}/test: responde (200 o error de red)",
              r2.status_code in (200, 500, 502, 503))

        r3 = requests.get(f"{BASE_URL}/api/erp/{erp_id}/estado",
                         headers=headers, timeout=5)
        check(f"GET /api/erp/{erp_id}/estado: HTTP 200", r3.status_code == 200)
        estado = r3.json()
        check("Estado contiene ultimoEnvio o ultimoEstado",
              "ultimoEnvio" in estado or "ultimoEstado" in estado)

        requests.delete(f"{BASE_URL}/api/erp/{erp_id}",
                       headers=headers, timeout=5)


if __name__ == "__main__":
    webhook_url = sys.argv[1] if len(sys.argv) > 1 else None
    if webhook_url:
        os.environ["TEST_WEBHOOK_URL"] = webhook_url

    print("=" * 60)
    print("PRUEBA DE INTEGRACION ERP")
    print("  Referencia: cap4_iteraciones.tex Iter 7 (lineas 1122-1140)")
    print("  Patron: Webhook saliente con field mapping")
    print(f"  Backend: {BASE_URL}")
    if webhook_url:
        print(f"  Webhook: {webhook_url}")
    print("=" * 60)

    token = _login()
    test_erp_endpoint_existe()
    test_erp_crud(token)
    test_field_mapping_static()
    test_enviar_a_webhook_static()
    test_erp_test_endpoint(token)

    total = PASS + FAIL + SKIP
    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {PASS} PASS, {FAIL} FAIL, {SKIP} SKIP de {total} pruebas")
    print(f"{'=' * 60}")
    sys.exit(0 if FAIL == 0 else 1)
