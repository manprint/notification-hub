import uuid

import pytest

from app.api.v1.groups import _receiver_counts
from app.schemas.group import (
    GroupChannelBindingCreate,
    GroupCreate,
    GroupOut,
    GroupUpdate,
)


@pytest.mark.unit
def test_group_create_schema():
    group_create = GroupCreate(
        name="Test Group",
        description="A test group",
    )

    assert group_create.name == "Test Group"
    assert group_create.description == "A test group"


@pytest.mark.unit
def test_group_create_schema_minimal():
    group_create = GroupCreate(name="Minimal")

    assert group_create.name == "Minimal"
    assert group_create.description is None


@pytest.mark.unit
def test_group_out_schema():
    group_out = GroupOut(
        id=str(uuid.uuid4()),
        name="Output Group",
        description="Test output",
        receiver_count=0,
    )

    assert group_out.name == "Output Group"
    assert group_out.description == "Test output"
    assert group_out.receiver_count == 0


@pytest.mark.unit
def test_group_out_schema_receiver_count():
    group_out = GroupOut(
        id=str(uuid.uuid4()),
        name="Output Group",
        description=None,
        receiver_count=3,
    )

    assert group_out.receiver_count == 3


@pytest.mark.unit
async def test_receiver_counts_returns_empty_for_no_ids():
    assert await _receiver_counts(None, uuid.UUID(int=1), []) == {}


@pytest.mark.unit
def test_group_update_schema():
    group_update = GroupUpdate(
        name="Updated Name",
        description="Updated description",
    )

    assert group_update.name == "Updated Name"
    assert group_update.description == "Updated description"


@pytest.mark.unit
def test_group_update_schema_partial():
    group_update = GroupUpdate(name="New Name")

    assert group_update.name == "New Name"
    assert group_update.description is None


@pytest.mark.unit
def test_group_channel_binding_create_schema():
    binding = GroupChannelBindingCreate(
        channel_id=str(uuid.uuid4()),
        min_severity="warning",
        enabled=True,
    )

    assert binding.channel_id
    assert binding.min_severity == "warning"
    assert binding.enabled is True


@pytest.mark.unit
def test_group_channel_binding_create_schema_default_enabled():
    binding = GroupChannelBindingCreate(
        channel_id=str(uuid.uuid4()),
        min_severity="info",
    )

    assert binding.enabled is True
