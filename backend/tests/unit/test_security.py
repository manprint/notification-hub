import pytest

from app.core.errors import Problem
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)


@pytest.mark.unit
def test_password_roundtrip():
    password = "test_password_123"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


@pytest.mark.unit
def test_hash_non_deterministico():
    password = "test_password_123"
    hash1 = hash_password(password)
    hash2 = hash_password(password)
    assert hash1 != hash2


@pytest.mark.unit
def test_refresh_token_hashato():
    token_plain, token_hash = new_refresh_token()
    assert len(token_plain) >= 40
    assert token_hash == hash_token(token_plain)


@pytest.mark.unit
def test_firma_alterata_rifiutata():
    user_id = "user-123"
    tenant_id = "tenant-123"
    role = "member"

    token, _ = create_access_token(user_id, tenant_id, role)
    tampered = token[:-5] + "xxxxx"

    with pytest.raises(Problem):
        decode_access_token(tampered)
