import uuid

import pytest

from app.services.storage import object_key, should_use_object_storage


@pytest.mark.unit
def test_should_use_object_storage_small_body():
    small_body = "x" * 1000
    assert not should_use_object_storage(len(small_body.encode()))


@pytest.mark.unit
def test_should_use_object_storage_boundary():
    threshold = 1048576
    assert not should_use_object_storage(threshold)
    assert should_use_object_storage(threshold + 1)


@pytest.mark.unit
def test_should_use_object_storage_large_body():
    large_body = "x" * 2_000_000
    assert should_use_object_storage(len(large_body.encode()))


@pytest.mark.unit
def test_object_key_has_tenant_prefix_and_date_partitioning():
    tenant_id = uuid.uuid4()
    notification_id = uuid.uuid4()

    key = object_key(tenant_id, notification_id)

    parts = key.split("/")
    assert parts[0] == str(tenant_id)
    assert len(parts) == 5
    assert parts[4] == f"{notification_id}.txt"
