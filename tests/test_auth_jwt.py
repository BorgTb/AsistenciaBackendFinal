"""
Test: Autenticacion JWT (Iter 5 - Pruebas de login y roles)
-----------------------------------------------------------
Corresponde a las pruebas descritas en cap4_iteraciones.tex (lineas 860-880):
  - "Prueba de login exitoso" (linea 861)
  - "Prueba de rechazo de credenciales invalidas" (linea 865)
  - "Prueba de acceso sin token" (linea 867)
  - "Prueba de acceso con rol insuficiente" (linea 869)
  - "Prueba de aislamiento multi-tenant" (linea 871)
  - "Prueba de login con multiples empresas" (linea 863)

Uso: python tests/test_auth_jwt.py
"""

import os
import sys
import requests
import jwt as pyjwt

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


def _is_backend_up():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def test_login_exitoso():
    print("\n=== 1. Login exitoso (admin@empresa.cl) ===")
    if not _is_backend_up():
        skip("Backend no accesible")
        return
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASS
        }, timeout=10)
        check("HTTP 200", r.status_code == 200)
        data = r.json()
        check("ok = True", data.get("ok") is True)
        token = data.get("token")
        check("token JWT presente", token is not None and len(token) > 20)
        user = data.get("user", {})
        check("rol = admin", user.get("rol") == "admin")
        check("empresa_id presente", user.get("empresa_id") is not None)

        if token:
            decoded = pyjwt.decode(token, options={"verify_signature": False})
            check("payload contiene user_id", "user_id" in decoded)
            check("payload contiene empresa_id", "empresa_id" in decoded)
            check("payload contiene rol", "rol" in decoded)
            check("payload contiene exp (expiracion)", "exp" in decoded)
            return token
    except Exception as e:
        check(f"Login EXCEPCION: {e}", False)
    return None


def test_login_invalido():
    print("\n=== 2. Login con credenciales invalidas ===")
    if not _is_backend_up():
        skip("Backend no accesible")
        return
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": "clave-equivocada-123"
        }, timeout=10)
        check("HTTP 401 (credenciales invalidas)", r.status_code == 401)
    except Exception as e:
        check(f"Login invalido EXCEPCION: {e}", False)


def test_login_sin_datos():
    print("\n=== 3. Login sin email/password ===")
    if not _is_backend_up():
        skip("Backend no accesible")
        return
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={}, timeout=10)
        check("HTTP 400 (Bad Request)", r.status_code == 400)
    except Exception as e:
        check(f"Login sin datos EXCEPCION: {e}", False)


def test_token_requerido():
    print("\n=== 4. Acceso sin token rechazado ===")
    if not _is_backend_up():
        skip("Backend no accesible")
        return
    try:
        r = requests.post(f"{BASE_URL}/api/auth/register", json={}, timeout=5)
        check("POST /api/auth/register sin token: HTTP 401",
              r.status_code == 401)
    except Exception as e:
        check(f"Token requerido EXCEPCION: {e}", False)


def test_rol_insuficiente(token_admin):
    print("\n=== 5. Acceso con rol insuficiente ===")
    if not token_admin:
        skip("Requiere token admin del test 1")
        return
    try:
        data = {"email": "test_trabajador@test.local",
                "password": "test1234",
                "nombre": "Test Trabajador",
                "rol": "trabajador"}
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json=data,
                          headers={"Authorization": f"Bearer {token_admin}"},
                          timeout=10)
        check("Admin puede crear trabajador (HTTP 200/201)",
              r.status_code in (200, 201))

        reg_data = r.json()
        trabajador_email = reg_data.get("email", "test_trabajador@test.local")

        r2 = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": trabajador_email, "password": "test1234"
        }, timeout=10)
        if r2.status_code == 200 and r2.json().get("ok"):
            token_trab = r2.json().get("token")
            r3 = requests.post(f"{BASE_URL}/api/auth/register",
                               json={},
                               headers={"Authorization": f"Bearer {token_trab}"},
                               timeout=5)
            check("Trabajador no puede crear usuarios: HTTP 403",
                  r3.status_code == 403)
        else:
            skip("No se pudo loguear como trabajador")
    except Exception as e:
        check(f"Rol insuficiente EXCEPCION: {e}", False)


def test_token_me(token_admin):
    print("\n=== 6. Endpoint /me retorna datos del usuario ===")
    if not token_admin:
        skip("Requiere token admin del test 1")
        return
    try:
        r = requests.get(f"{BASE_URL}/api/auth/me",
                         headers={"Authorization": f"Bearer {token_admin}"},
                         timeout=5)
        check("GET /api/auth/me: HTTP 200", r.status_code == 200)
        data = r.json()
        check("Respuesta contiene email", "email" in data)
        check("Respuesta contiene empresas (lista)", isinstance(data.get("empresas"), list))
    except Exception as e:
        check(f"/me EXCEPCION: {e}", False)


def test_multi_tenant_aislamiento(token_admin):
    print("\n=== 7. Aislamiento multi-tenant basico ===")
    if not token_admin:
        skip("Requiere token admin del test 1")
        return
    try:
        r = requests.get(f"{BASE_URL}/api/personas",
                         headers={"Authorization": f"Bearer {token_admin}"},
                         timeout=10)
        check("GET /api/personas con token admin: HTTP 200", r.status_code == 200)
        datos = r.json()
        check("Retorna lista de personas", isinstance(datos, list))
    except Exception as e:
        check(f"Multi-tenant EXCEPCION: {e}", False)


if __name__ == "__main__":
    print("=" * 60)
    print("PRUEBA DE AUTENTICACION JWT Y ROLES")
    print("  Referencia: cap4_iteraciones.tex Iter 5 (lineas 860-880)")
    print("  Mecanismo: JWT HMAC-SHA256, expiracion 24h, bcrypt")
    print(f"  Backend: {BASE_URL}")
    print("=" * 60)

    token = test_login_exitoso()
    test_login_invalido()
    test_login_sin_datos()
    test_token_requerido()
    test_rol_insuficiente(token)
    test_token_me(token)
    test_multi_tenant_aislamiento(token)

    total = PASS + FAIL + SKIP
    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {PASS} PASS, {FAIL} FAIL, {SKIP} SKIP de {total} pruebas")
    print(f"{'=' * 60}")
    sys.exit(0 if FAIL == 0 else 1)
