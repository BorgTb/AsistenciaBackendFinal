import os
import hashlib
import base64
from cryptography.fernet import Fernet

BIOMETRIC_KEY = os.getenv("BIOMETRIC_KEY", "cambia-esta-clave-biometrica-en-produccion")

def _derivar_fernet_key() -> bytes:
    digest = hashlib.sha256(BIOMETRIC_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)

_fernet = Fernet(_derivar_fernet_key())

def cifrar_embedding(embedding: list) -> str:
    from json import dumps
    plano = dumps(embedding).encode("utf-8")
    cifrado = _fernet.encrypt(plano)
    return base64.urlsafe_b64encode(cifrado).decode("ascii")

def descifrar_embedding(cifrado_str: str) -> list:
    from json import loads

    if not cifrado_str:
        return None

    try:
        cifrado = base64.urlsafe_b64decode(cifrado_str.encode("ascii"))
        plano = _fernet.decrypt(cifrado)
        return loads(plano.decode("utf-8"))
    except Exception:
        return loads(cifrado_str)
