import uuid
from datetime import datetime

import pytest

from app.models.api_key import ApiKey


@pytest.mark.unit
def test_api_key_model_creation():
    receiver_id = uuid.uuid4()
    key_hash = "abcd1234" * 8
    created_at = datetime.utcnow()

    api_key = ApiKey(
        id=uuid.uuid4(),
        receiver_id=receiver_id,
        key_hash=key_hash,
        label="Production Key",
        created_at=created_at,
        last_used_at=None,
        revoked_at=None,
    )

    assert api_key.receiver_id == receiver_id
    assert api_key.key_hash == key_hash
    assert api_key.label == "Production Key"
    assert api_key.last_used_at is None
    assert api_key.revoked_at is None


@pytest.mark.unit
def test_api_key_revoked():
    receiver_id = uuid.uuid4()
    revoked_at = datetime.utcnow()

    api_key = ApiKey(
        id=uuid.uuid4(),
        receiver_id=receiver_id,
        key_hash="hash" * 16,
        label="Revoked Key",
        created_at=datetime.utcnow(),
        last_used_at=datetime.utcnow(),
        revoked_at=revoked_at,
    )

    assert api_key.revoked_at is not None
    assert api_key.revoked_at == revoked_at


@pytest.mark.unit
def test_api_key_last_used_tracking():
    last_used = datetime.utcnow()

    api_key = ApiKey(
        id=uuid.uuid4(),
        receiver_id=uuid.uuid4(),
        key_hash="x" * 64,
        label="Test Key",
        created_at=datetime.utcnow(),
        last_used_at=last_used,
        revoked_at=None,
    )

    assert api_key.last_used_at == last_used
