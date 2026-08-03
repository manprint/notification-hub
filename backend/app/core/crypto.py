import os
from hashlib import sha256
from urllib.parse import urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


def encrypt_secret(plaintext: str) -> bytes:
    settings = get_settings()
    key = sha256(settings.notifyhub_secret_key.encode()).digest()
    nonce = os.urandom(12)
    cipher = AESGCM(key)
    ciphertext = cipher.encrypt(nonce, plaintext.encode(), None)
    return nonce + ciphertext


def decrypt_secret(blob: bytes) -> str:
    settings = get_settings()
    key = sha256(settings.notifyhub_secret_key.encode()).digest()
    nonce = blob[:12]
    ciphertext = blob[12:]
    cipher = AESGCM(key)
    plaintext = cipher.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


def mask_webhook(url: str) -> str:
    """Suggerimento mostrato nella UI: schema, host e le ultime 4 cifre.

    L'implementazione precedente restituiva `url[:-4] + "/...//" + url[-4:]`,
    cioe l'URL completo con un separatore infilato dentro: il path del webhook
    (che e l'intero segreto) finiva in chiaro nella lista dei canali.
    """
    if len(url) <= 8:
        return "***"
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.hostname}" if parsed.scheme and parsed.hostname else ""
    return f"{host}/***{url[-4:]}"
