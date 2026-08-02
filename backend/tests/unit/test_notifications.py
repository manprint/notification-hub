import uuid
from datetime import UTC, datetime

import pytest

from app.schemas.notification import (
    BulkReadIn,
    MarkStatusIn,
    NotificationListItemOut,
)


@pytest.mark.unit
def test_notification_list_item_schema():
    now = datetime.now(UTC)
    item = NotificationListItemOut(
        id=str(uuid.uuid4()),
        receiver_id=str(uuid.uuid4()),
        content_preview="Preview text",
        content_size=12,
        content_normalized=False,
        storage_backend="inline",
        severity="info",
        severity_source="receiver_default",
        status="unread",
        received_at=now,
    )
    assert item.status == "unread"
    assert item.severity == "info"


@pytest.mark.unit
def test_mark_status_schema():
    body = MarkStatusIn(status="read")
    assert body.status == "read"


@pytest.mark.unit
def test_bulk_read_schema_accepts_from_alias():
    body = BulkReadIn.model_validate(
        {"group_id": str(uuid.uuid4()), "from": "2026-01-01T00:00:00Z"}
    )
    assert body.group_id is not None
    assert body.from_ is not None
