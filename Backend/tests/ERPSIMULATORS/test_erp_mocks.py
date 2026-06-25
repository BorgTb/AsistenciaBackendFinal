"""
test_erp_mocks.py
=================
Script de prueba de integración que valida los tres mocks ERP
contra tu sistema SAS. Ejecuta cada caso de prueba de la tesis
y muestra un reporte final con los resultados.

Uso:
  # Primero levanta los mocks en terminales separadas:
  #   python mock_odoo.py      → puerto 8001
  #   python mock_defontana.py → puerto 8002
  #   python mock_buk.py       → puerto 8003

  python test_erp_mocks.py

Requisito:
  pip install requests
"""

import requests
import json
from datetime import datetime, timezone

# ── Configuración de los mocks ────────────────────────────────────────────────
MOCKS = {
    "Odoo":       "http://localhost:8001",
    "Defontana":  "http://localhost:8002",
    "Buk":        "http://localhost:8003",
}

# Payload estándar que genera tu sistema SAS
MARCAJE_SAS = {
    "rut":       "12.345.678-9",
    "nombre":    "Juan Pérez",
    "tipo":      "entrada",
    "metodo":    "huella",
    "fecha_hora": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}

resultados = []   # lista de (nombre_prueba, ok, detalle)


def log(ok: bool, nombre: str, detalle: str):
    estado = "✓ PASS" if ok else "✗ FAIL"
    print(f"  {estado}  {nombre}")
    if not ok:
        print(f"         → {detalle}")
    resultados.append((nombre, ok, detalle))


# ══════════════════════════════════════════════════════════════════════════════
# ODOO — JSON-RPC
# ══════════════════════════════════════════════════════════════════════════════
def test_odoo():
    base = MOCKS["Odoo"]
    print("\n📦 ODOO (http://localhost:8001)")
    print("   API: JSON-RPC — /web/dataset/call_kw")
    print("   Docs: https://www.odoo.com/documentation/\n")

    # T1: Health check
    try:
        r = requests.get(f"{base}/health", timeout=3)
        log(r.status_code == 200, "Odoo – Health check", r.text[:80])
    except Exception as e:
        log(False, "Odoo – Health check", f"Servidor no disponible: {e}")
        return

    # T2: Autenticación JSON-RPC
    auth_payload = {
        "jsonrpc": "2.0", "method": "call", "id": 1,
        "params": {"db": "odoo_test", "login": "admin", "password": "admin"}
    }
    r = requests.post(f"{base}/web/session/authenticate", json=auth_payload)
    ok = r.status_code == 200 and "uid" in r.json().get("result", {})
    log(ok, "Odoo – Autenticación JSON-RPC", r.text[:120])
    session_cookies = r.cookies if ok else {}

    # T3: Buscar empleados (hr.employee)
    payload = {
        "jsonrpc": "2.0", "method": "call", "id": 2,
        "params": {
            "model": "hr.employee", "method": "search_read",
            "args": [], "kwargs": {"fields": ["id", "name", "rut"], "limit": 10}
        }
    }
    r = requests.post(f"{base}/web/dataset/call_kw", json=payload, cookies=session_cookies)
    data = r.json()
    ok = r.status_code == 200 and isinstance(data.get("result"), list)
    log(ok, "Odoo – Listar empleados (hr.employee)", f"{len(data.get('result',[]))} empleados")

    # T4: Crear asistencia (hr.attendance) — payload nativo Odoo
    payload = {
        "jsonrpc": "2.0", "method": "call", "id": 3,
        "params": {
            "model": "hr.attendance", "method": "create",
            "args": [{"employee_id": 1, "check_in": MARCAJE_SAS["fecha_hora"]}],
            "kwargs": {}
        }
    }
    r = requests.post(f"{base}/web/dataset/call_kw", json=payload, cookies=session_cookies)
    data = r.json()
    ok = r.status_code == 200 and isinstance(data.get("result"), int)
    log(ok, "Odoo – Crear marcaje (hr.attendance)", f"id={data.get('result')}")

    # T5: Endpoint REST simplificado con field_map de SAS
    field_mapped = {
        "employee_rut":  MARCAJE_SAS["rut"],
        "check_type":    MARCAJE_SAS["tipo"],
        "datetime":      MARCAJE_SAS["fecha_hora"],
        "employee_name": MARCAJE_SAS["nombre"],
    }
    r = requests.post(f"{base}/api/attendance", json=field_mapped)
    ok = r.status_code == 200 and r.json().get("ok") is True
    log(ok, "Odoo – Marcaje via REST con field_map SAS", r.text[:120])

    # T6: Tolerancia a fallo (empleado inexistente)
    payload = {
        "jsonrpc": "2.0", "method": "call", "id": 4,
        "params": {
            "model": "hr.attendance", "method": "create",
            "args": [{"employee_id": 9999, "check_in": MARCAJE_SAS["fecha_hora"]}],
            "kwargs": {}
        }
    }
    r = requests.post(f"{base}/web/dataset/call_kw", json=payload, cookies=session_cookies)
    ok = r.status_code == 400 and "error" in r.json()
    log(ok, "Odoo – Error: empleado inexistente retorna error", r.json().get("error", {}).get("message","")[:80])


# ══════════════════════════════════════════════════════════════════════════════
# DEFONTANA — REST + JWT
# ══════════════════════════════════════════════════════════════════════════════
def test_defontana():
    base = MOCKS["Defontana"]
    print("\n📦 DEFONTANA (http://localhost:8002)")
    print("   API: REST — /api/Login/GetByCredentials + /api/Employee/AddAttendance")
    print("   Docs: https://defontana.atlassian.net/wiki/spaces/CDAV2/")
    print("   Swagger pruebas: https://replapi.defontana.com/swagger/index.html\n")

    # T1: Health check
    try:
        r = requests.get(f"{base}/health", timeout=3)
        log(r.status_code == 200, "Defontana – Health check", r.text[:80])
    except Exception as e:
        log(False, "Defontana – Health check", f"Servidor no disponible: {e}")
        return

    # T2: Autenticación
    creds = {"username": "admin", "password": "Defontana2025!", "company": "dfchile"}
    r = requests.post(f"{base}/api/Login/GetByCredentials", json=creds)
    data = r.json()
    ok = r.status_code == 200 and data.get("success") and data.get("authResult", {}).get("access_token")
    token = data.get("authResult", {}).get("access_token", "") if ok else ""
    log(ok, "Defontana – Login (JWT Bearer)", f"token={token[:16]}...")

    headers = {
        "Authorization":  f"Bearer {token}",
        "Content-Type":   "application/json",
        "X-Company-Id":   "dfchile",
    }

    # T3: Listar empleados
    r = requests.get(f"{base}/api/Employee/GetAll", headers=headers)
    ok = r.status_code == 200 and "items" in r.json()
    log(ok, "Defontana – Listar empleados", f"{r.json().get('totalItems',0)} empleados")

    # T4: Marcaje con field_map de SAS (tipoMarcaje, rutEmpleado, fechaHoraMarcaje)
    payload_mapeado = {
        "rutEmpleado":      MARCAJE_SAS["rut"],      # field_map: rut → rutEmpleado
        "tipoMarcaje":      1,                        # field_map: tipo → tipoMarcaje (1=entrada)
        "fechaHoraMarcaje": MARCAJE_SAS["fecha_hora"],# field_map: fecha_hora → fechaHoraMarcaje
        "codigoEmpresa":    "dfchile",
        "origen":           "biometrico",
    }
    r = requests.post(f"{base}/api/Employee/AddAttendance", json=payload_mapeado, headers=headers)
    ok = r.status_code == 200 and r.json().get("success")
    log(ok, "Defontana – Registrar marcaje AddAttendance", r.text[:140])

    # T5: Marcaje con campo "tipo" sin mapear (tolerancia del mock)
    payload_sin_map = {
        "rutEmpleado":      MARCAJE_SAS["rut"],
        "tipoMarcaje":      "salida",   # string en vez de int
        "fechaHoraMarcaje": MARCAJE_SAS["fecha_hora"],
    }
    r = requests.post(f"{base}/api/Employee/AddAttendance", json=payload_sin_map, headers=headers)
    ok = r.status_code == 200 and r.json().get("success")
    log(ok, "Defontana – Tolerancia: tipo como string", r.json().get("data", {}).get("descripcionTipo",""))

    # T6: Sin token → 401
    r = requests.post(f"{base}/api/Employee/AddAttendance", json=payload_mapeado)
    ok = r.status_code == 401
    log(ok, "Defontana – Sin token retorna 401", r.text[:80])

    # T7: RUT inexistente → 422
    bad_payload = {**payload_mapeado, "rutEmpleado": "99.999.999-9"}
    r = requests.post(f"{base}/api/Employee/AddAttendance", json=bad_payload, headers=headers)
    ok = r.status_code == 422
    log(ok, "Defontana – RUT inexistente retorna 422", r.text[:80])

    # T8: Consultar marcajes
    r = requests.get(f"{base}/api/Employee/GetAttendance",
                     params={"desde": "2025-06-01", "hasta": "2025-06-30"},
                     headers=headers)
    ok = r.status_code == 200 and "items" in r.json()
    log(ok, "Defontana – Consultar marcajes del período", f"{r.json().get('totalItems',0)} registros")


# ══════════════════════════════════════════════════════════════════════════════
# BUK — REST con auth_token
# ══════════════════════════════════════════════════════════════════════════════
def test_buk():
    base = MOCKS["Buk"]
    print("\n📦 BUK ASISTENCIA (http://localhost:8003)")
    print("   API: REST — Header auth_token + /attendances/inject")
    print("   Docs:    https://supportcenter.buk.cl/hc/es-419/articles/50240904785051")
    print("   Swagger: https://app.swaggerhub.com/apis-docs/BUKASISTENCIA/ApiAsistencia/1.0.0\n")

    TOKEN = "MI_TOKEN_BUK"
    headers = {"auth_token": TOKEN, "Content-Type": "application/json"}

    # T1: Health check
    try:
        r = requests.get(f"{base}/health", timeout=3)
        log(r.status_code == 200, "Buk – Health check", r.text[:80])
    except Exception as e:
        log(False, "Buk – Health check", f"Servidor no disponible: {e}")
        return

    # T2: Sin token → 401
    r = requests.get(f"{base}/employees")
    ok = r.status_code == 401
    log(ok, "Buk – Sin auth_token retorna 401", r.text[:80])

    # T3: Listar empleados
    r = requests.get(f"{base}/employees", headers=headers)
    ok = r.status_code == 200 and "data" in r.json()
    log(ok, "Buk – Listar empleados", f"{r.json().get('pagination',{}).get('count',0)} empleados")

    # T4: Listar recintos (necesario para premise_id)
    r = requests.get(f"{base}/premises", headers=headers)
    ok = r.status_code == 200
    log(ok, "Buk – Listar recintos", str(r.json().get("data",[])))

    # T5: Inyección de marcaje con field_map SAS
    payload = {
        "rut":        MARCAJE_SAS["rut"],        # igual, no requiere mapeo
        "type":       "in",                       # field_map: tipo → type
        "datetime":   MARCAJE_SAS["fecha_hora"],  # field_map: fecha_hora → datetime
        "premise_id": 1,
    }
    r = requests.post(f"{base}/attendances/inject", json=payload, headers=headers)
    ok = r.status_code == 200 and r.json().get("status") == "injected"
    log(ok, "Buk – Inyectar marcaje (entrada)", r.text[:140])

    # T6: Inyección de salida
    payload_salida = {**payload, "type": "out"}
    r = requests.post(f"{base}/attendances/inject", json=payload_salida, headers=headers)
    ok = r.status_code == 200 and r.json().get("status") == "injected"
    log(ok, "Buk – Inyectar marcaje (salida)", r.text[:140])

    # T7: Tipo sin mapear ("entrada" directo)
    payload_sin_map = {**payload, "type": "entrada"}  # sin field_map aplicado
    r = requests.post(f"{base}/attendances/inject", json=payload_sin_map, headers=headers)
    ok = r.status_code == 200
    log(ok, "Buk – Tolerancia: tipo 'entrada' sin mapear", r.text[:100])

    # T8: RUT inexistente → 422
    bad = {**payload, "rut": "99.999.999-9"}
    r = requests.post(f"{base}/attendances/inject", json=bad, headers=headers)
    ok = r.status_code == 422
    log(ok, "Buk – RUT inexistente retorna 422", r.text[:80])

    # T9: Consultar marcajes del período
    r = requests.get(f"{base}/attendances",
                     params={"desde": "2025-06-01", "hasta": "2025-06-30"}, headers=headers)
    ok = r.status_code == 200 and "data" in r.json()
    log(ok, "Buk – Consultar marcajes del período", f"{r.json().get('pagination',{}).get('count',0)} registros")


# ══════════════════════════════════════════════════════════════════════════════
# REPORTE FINAL
# ══════════════════════════════════════════════════════════════════════════════
def reporte():
    total  = len(resultados)
    passed = sum(1 for _, ok, _ in resultados if ok)
    failed = total - passed

    print("\n" + "═" * 60)
    print("  REPORTE DE PRUEBAS DE INTEGRACIÓN ERP")
    print("═" * 60)
    print(f"  Total:   {total}")
    print(f"  ✓ Passed: {passed}")
    print(f"  ✗ Failed: {failed}")
    print(f"  Tasa de éxito: {passed/total*100:.0f}%")

    if failed > 0:
        print("\n  Pruebas fallidas:")
        for nombre, ok, detalle in resultados:
            if not ok:
                print(f"    - {nombre}")
                print(f"      {detalle}")

    print("\n  Resumen por ERP:")
    for erp in ["Odoo", "Defontana", "Buk"]:
        sub  = [(n,ok,d) for n,ok,d in resultados if n.startswith(erp)]
        sp   = sum(1 for _,ok,_ in sub if ok)
        print(f"    {erp:12s}: {sp}/{len(sub)} pruebas pasadas")

    print("═" * 60)
    return failed == 0


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  PRUEBAS DE INTEGRACIÓN — MOCKS ERP                 ║")
    print("║  Sistema SAS × Odoo × Defontana × Buk               ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"\n  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Payload de prueba: {json.dumps(MARCAJE_SAS, ensure_ascii=False)}")

    test_odoo()
    test_defontana()
    test_buk()
    ok = reporte()

    exit(0 if ok else 1)
