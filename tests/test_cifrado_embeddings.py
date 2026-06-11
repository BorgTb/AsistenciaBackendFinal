"""
Test: Cifrado de Embeddings Biométricos (Iter 4 - Prueba de cifrado y descifrado)
-------------------------------------------------------------------------------
Corresponde a la prueba descrita en cap4_iteraciones.tex (linea 745):
  - "Prueba de cifrado y descifrado": Almacenar un embedding y verificar
    que el valor en BD no sea legible en texto plano. Luego descifrar y
    verificar que el vector original se reconstruya idénticamente.

Verifica:
  1. Cifrado Fernet produce texto no legible (no contiene floats planos)
  2. Descifrado reconstruye el vector exacto (float por float)
  3. Round-trip cifrar -> descifrar es determinista
  4. Doble cifrado del mismo vector produce distinto ciphertext (IV aleatorio)
  5. Modificacion del ciphertext provoca error de descifrado

Uso: python tests/test_cifrado_embeddings.py
"""

import os
import sys
import base64
import hashlib
from json import dumps, loads

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Backend'))
os.environ.setdefault("BIOMETRIC_KEY", "cambia-esta-clave-biometrica-en-produccion")

from encryption import cifrar_embedding, descifrar_embedding

PASS = 0
FAIL = 0


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


def test_roundtrip():
    print("\n=== 1. Round-trip cifrar -> descifrar ===")
    original = [0.123456, -0.987654, 0.5, -0.333333] * 32
    cifrado = cifrar_embedding(original)
    check("cifrar_embedding retorna string", isinstance(cifrado, str))
    check("Ciphertext NO contiene numeros planos",
          all(str(v) not in cifrado for v in original[:4]))
    check("Ciphertext es Base64 URL-safe decodificable",
          base64.urlsafe_b64decode(cifrado.encode()))
    descifrado = descifrar_embedding(cifrado)
    check("descifrar_embedding retorna lista", isinstance(descifrado, list))
    check(f"Misma longitud ({len(original)} elementos)",
          len(descifrado) == len(original))
    iguales = all(abs(a - b) < 1e-9 for a, b in zip(original, descifrado))
    check("Vector reconstruido identico (float por float)", iguales)


def test_no_determinista():
    print("\n=== 2. Cifrado NO determinista (IV por mensaje) ===")
    embedding = [0.0, 1.0, -0.5] * 43
    c1 = cifrar_embedding(embedding)
    c2 = cifrar_embedding(embedding)
    check("Dos cifrados del mismo vector son distintos",
          c1 != c2)
    d1 = descifrar_embedding(c1)
    d2 = descifrar_embedding(c2)
    check("Ambos descifran al mismo vector",
          d1 == d2)


def test_corrupcion():
    print("\n=== 3. Resistencia a corrupcion ===")
    embedding = [0.111] * 128
    cifrado = cifrar_embedding(embedding)
    raw = base64.urlsafe_b64decode(cifrado.encode())
    modificado = raw[:len(raw) // 2] + bytes([raw[len(raw) // 2] ^ 0xFF]) + raw[len(raw) // 2 + 1:]
    corrupto = base64.urlsafe_b64encode(modificado).decode()
    try:
        result = descifrar_embedding(corrupto)
        check("Ciphertext corrupto es rechazado", False)
    except Exception:
        check("Ciphertext corrupto lanza excepcion (HMAC no coincide)", True)


def test_embedding_vacio():
    print("\n=== 4. Caso borde: embedding vacio ===")
    check("descifrar_embedding(None) -> None",
          descifrar_embedding(None) is None)
    check("descifrar_embedding('') -> None",
          descifrar_embedding("") is None)


def test_fernet_key_derivation():
    print("\n=== 5. Derivacion de clave Fernet ===")
    from encryption import _derivar_fernet_key
    from cryptography.fernet import Fernet
    key = _derivar_fernet_key()
    check("Clave derivada tiene 44 chars (Base64 de 32 bytes)",
          len(key) == 44)
    f = Fernet(key)
    token = f.encrypt(b"hola")
    check("Fernet con clave derivada funciona", f.decrypt(token) == b"hola")


if __name__ == "__main__":
    print("=" * 60)
    print("PRUEBA DE CIFRADO DE EMBEDDINGS BIOMETRICOS")
    print("  Referencia: cap4_iteraciones.tex Iter 4 (linea 745)")
    print("  Algoritmo: Fernet (AES-128 CBC + HMAC-SHA256)")
    print("=" * 60)

    test_roundtrip()
    test_no_determinista()
    test_corrupcion()
    test_embedding_vacio()
    test_fernet_key_derivation()

    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {PASS} PASS, {FAIL} FAIL de {PASS + FAIL} pruebas")
    print(f"{'=' * 60}")
    sys.exit(0 if FAIL == 0 else 1)
