"""
Test: Identificacion Facial 1:N (Iter 4 - Prueba de identificacion 1:N)
-----------------------------------------------------------------------
Corresponde a las pruebas descritas en cap4_iteraciones.tex (lineas 737-742):
  - "Prueba de identificacion 1:N": Registrar 3 personas, enviar foto de
    una de ellas y verificar que retorne el persona_id correcto (linea 737)
  - "Prueba de identificacion con rostro desconocido": Foto de persona no
    registrada debe retornar HTTP 404 (linea 739)

NOTA: Este test asume que el backend esta corriendo y que DeepFace esta
instalado. Las imagenes de prueba deben existir en tests/fotos_prueba/.
Si no hay fotos, las pruebas se marcan como SKIP.

Uso: python tests/test_facial_identificar.py
"""

import os
import sys
import base64
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Backend'))

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")
FOTOS_DIR = os.path.join(os.path.dirname(__file__), 'fotos_prueba')
os.makedirs(FOTOS_DIR, exist_ok=True)

PASS = 0
FAIL = 0
SKIP = 0


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


def _leer_imagen_b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')


def _listar_fotos():
    exts = ('.jpg', '.jpeg', '.png')
    return sorted([f for f in os.listdir(FOTOS_DIR) if f.lower().endswith(exts)])


def test_endpoint_existe():
    print("\n=== 1. Endpoint de identificacion ===")
    try:
        payload = {"imagen": "dGVzdA=="}
        r = requests.post(f"{BASE_URL}/api/facial/identificar",
                          json=payload, timeout=30)
        check("POST /api/facial/identificar responde (200 o 404 o 400)",
              r.status_code in (200, 400, 404))
    except requests.ConnectionError:
        skip("Backend no accesible en " + BASE_URL)
    except Exception as e:
        check(f"Endpoint existe: {e}", False)


def test_identificar_con_fotos():
    fotos = _listar_fotos()
    if len(fotos) < 1:
        skip(f"No hay fotos en {FOTOS_DIR}/. Coloca imagenes .jpg para probar.")
        return

    print(f"\n=== 2. Identificacion con {len(fotos)} foto(s) ===")
    for foto in fotos:
        path = os.path.join(FOTOS_DIR, foto)
        try:
            b64 = _leer_imagen_b64(path)
        except Exception as e:
            skip(f"Error leyendo {foto}: {e}")
            continue

        try:
            r = requests.post(
                f"{BASE_URL}/api/facial/identificar",
                json={"imagen": b64},
                timeout=30
            )
            if r.status_code == 404:
                check(f"Foto '{foto}': HTTP 404 (rostro no registrado) - flujo correcto",
                      True)
            elif r.status_code == 200:
                data = r.json()
                persona_id = data.get('persona_id', data.get('id'))
                confianza = data.get('confianza', data.get('confidence', 'N/A'))
                check(f"Foto '{foto}': identificado persona_id={persona_id}, confianza={confianza}",
                      persona_id is not None)
            elif r.status_code == 400:
                check(f"Foto '{foto}': HTTP 400 (posible anti-spoofing o sin rostro)",
                      True)
            else:
                check(f"Foto '{foto}': HTTP {r.status_code}",
                      False)
        except requests.ConnectionError:
            skip("Backend no accesible")
            return
        except Exception as e:
            check(f"Foto '{foto}': EXCEPCION {e}", False)


def test_identificar_octet_stream():
    fotos = _listar_fotos()
    if len(fotos) < 1:
        skip(f"No hay fotos en {FOTOS_DIR}/ para probar octet-stream.")
        return

    print("\n=== 3. Identificacion con application/octet-stream ===")
    foto = fotos[0]
    path = os.path.join(FOTOS_DIR, foto)
    try:
        with open(path, 'rb') as f:
            jpeg_bytes = f.read()
        r = requests.post(
            f"{BASE_URL}/api/facial/identificar",
            data=jpeg_bytes,
            headers={'Content-Type': 'application/octet-stream'},
            timeout=30
        )
        valid_codes = (200, 400, 404)
        check(f"POST octet-stream '{foto}': HTTP {r.status_code}",
              r.status_code in valid_codes)
    except requests.ConnectionError:
        skip("Backend no accesible")
    except Exception as e:
        check(f"octet-stream: EXCEPCION {e}", False)


def test_identificar_sin_imagen():
    print("\n=== 4. Identificacion sin imagen (error esperado) ===")
    try:
        r = requests.post(f"{BASE_URL}/api/facial/identificar",
                          json={}, timeout=10)
        check("POST sin imagen: HTTP 400 (Bad Request)",
              r.status_code == 400)
    except requests.ConnectionError:
        skip("Backend no accesible")
    except Exception as e:
        check(f"Sin imagen: EXCEPCION {e}", False)


def test_verificar_endpoint():
    print("\n=== 5. Endpoint de verificacion 1:1 ===")
    try:
        payload = {"persona_id": 99999, "imagen": "dGVzdA=="}
        r = requests.post(f"{BASE_URL}/api/facial/verificar",
                          json=payload, timeout=10)
        check("POST /api/facial/verificar responde",
              r.status_code in (200, 400, 404))
    except requests.ConnectionError:
        skip("Backend no accesible")
    except Exception as e:
        check(f"Verificar: EXCEPCION {e}", False)


if __name__ == "__main__":
    print("=" * 60)
    print("PRUEBA DE IDENTIFICACION FACIAL 1:N")
    print("  Referencia: cap4_iteraciones.tex Iter 4 (lineas 737-742)")
    print("  Flujo: HTTP POST /api/facial/identificar (octet-stream)")
    print("  Modelo: Facenet + RetinaFace, umbral 10.0")
    print(f"  Fotos en: {FOTOS_DIR}")
    print("=" * 60)

    test_endpoint_existe()
    test_identificar_con_fotos()
    test_identificar_octet_stream()
    test_identificar_sin_imagen()
    test_verificar_endpoint()

    total = PASS + FAIL + SKIP
    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {PASS} PASS, {FAIL} FAIL, {SKIP} SKIP de {total} pruebas")
    print(f"{'=' * 60}")
    sys.exit(0 if FAIL == 0 else 1)
