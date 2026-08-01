import os
from hashlib import sha256

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
    if len(url) <= 8:
        return url
    return url[: len(url) - 4] + "/...//" + url[-4:]
