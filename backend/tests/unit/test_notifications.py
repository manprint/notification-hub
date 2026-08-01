import uuid

import pytest

from app.schemas.notification import (
    ArchiveRequest,
    MarkReadRequest,
    MarkUnreadRequest,
    NotificationOut,
)


@pytest.mark.unit
def test_mark_read_request_schema():
    req = MarkReadRequest(notification_ids=[str(uuid.uuid4()), str(uuid.uuid4())])

    assert len(req.notification_ids) == 2


@pytest.mark.unit
def test_mark_read_request_schema_empty():
    req = MarkReadRequest(notification_ids=[])

    assert len(req.notification_ids) == 0


@pytest.mark.unit
def test_mark_unread_request_schema():
    req = MarkUnreadRequest(notification_ids=[str(uuid.uuid4())])

    assert len(req.notification_ids) == 1


@pytest.mark.unit
def test_archive_request_schema():
    req = ArchiveRequest(notification_ids=[str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())])

    assert len(req.notification_ids) == 3


@pytest.mark.unit
def test_notification_out_schema():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    notification = NotificationOut(
        id=str(uuid.uuid4()),
        title="Test Notification",
        content_preview="Preview text",
        severity="info",
        status="unread",
        received_at=now,
    )

    assert notification.title == "Test Notification"
    assert notification.status == "unread"
    assert notification.archived_at is None


@pytest.mark.unit
def test_notification_out_schema_archived():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    notification = NotificationOut(
        id=str(uuid.uuid4()),
        title="Archived Notification",
        content_preview="Preview",
        severity="warning",
        status="read",
        received_at=now,
        archived_at=now,
    )

    assert notification.archived_at == now
