import uuid

import pytest

from app.services.storage import should_use_object_storage


@pytest.mark.unit
def test_notification_storage_backend_threshold():
    settings_threshold = 20971520 // 2

    small_body = "x" * (settings_threshold - 1)
    assert not should_use_object_storage(len(small_body.encode()))

    large_body = "x" * (settings_threshold + 1)
    assert should_use_object_storage(len(large_body.encode()))


@pytest.mark.unit
def test_notification_storage_backend_boundary():
    threshold = 20971520 // 2

    exactly_at_threshold = "x" * threshold
    assert not should_use_object_storage(len(exactly_at_threshold.encode()))

    just_over_threshold = "x" * (threshold + 1)
    assert should_use_object_storage(len(just_over_threshold.encode()))


@pytest.mark.unit
def test_receiver_auth_dataclass_uuid():
    receiver_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    from app.services.ingestion import ReceiverAuth

    auth = ReceiverAuth(
        receiver_id=receiver_id,
        tenant_id=tenant_id,
        max_body_bytes=1000000,
        rate_limit_per_min=100,
    )

    assert isinstance(auth.receiver_id, uuid.UUID)
    assert isinstance(auth.tenant_id, uuid.UUID)
