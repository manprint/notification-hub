import pytest
from cryptography.exceptions import InvalidTag

from app.core.crypto import decrypt_secret, encrypt_secret, mask_webhook


@pytest.mark.unit
def test_roundtrip():
    url = "https://hooks.slack.com/services/T000/B000/XYZSEGRETO"
    encrypted = encrypt_secret(url)
    decrypted = decrypt_secret(encrypted)
    assert decrypted == url


@pytest.mark.unit
def test_nonce_diverso_ogni_volta():
    plaintext = "https://hooks.slack.com/services/T000/B000/XYZSEGRETO"
    blob1 = encrypt_secret(plaintext)
    blob2 = encrypt_secret(plaintext)
    assert blob1 != blob2


@pytest.mark.unit
def test_manomissione_rilevata():
    plaintext = "https://hooks.slack.com/services/T000/B000/XYZSEGRETO"
    blob = encrypt_secret(plaintext)
    tampered = bytearray(blob)
    tampered[0] ^= 1
    tampered = bytes(tampered)

    with pytest.raises(InvalidTag):
        decrypt_secret(tampered)


@pytest.mark.unit
def test_mask_webhook_non_rivela_il_segreto():
    url = "https://hooks.slack.com/services/T000/B000/XYZSEGRETO"
    masked = mask_webhook(url)
    assert "XYZSEGRETO" not in masked
    assert masked.endswith("RETO")
