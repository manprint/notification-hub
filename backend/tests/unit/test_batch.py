import uuid

import pytest

from app.schemas.batch import (
    BulkArchiveRequest,
    BulkDeleteRequest,
    BulkMarkReadRequest,
    BulkMarkUnreadRequest,
    BulkOperationResponse,
)


@pytest.mark.unit
def test_bulk_mark_read_request():
    req = BulkMarkReadRequest(notification_ids=[str(uuid.uuid4())])

    assert len(req.notification_ids) == 1


@pytest.mark.unit
def test_bulk_mark_unread_request():
    req = BulkMarkUnreadRequest(notification_ids=[str(uuid.uuid4()), str(uuid.uuid4())])

    assert len(req.notification_ids) == 2


@pytest.mark.unit
def test_bulk_archive_request():
    req = BulkArchiveRequest(notification_ids=[str(uuid.uuid4())])

    assert len(req.notification_ids) == 1


@pytest.mark.unit
def test_bulk_delete_request():
    ids = [str(uuid.uuid4()) for _ in range(5)]
    req = BulkDeleteRequest(notification_ids=ids)

    assert len(req.notification_ids) == 5


@pytest.mark.unit
def test_bulk_operation_response():
    response = BulkOperationResponse(
        processed=10,
        failed=2,
        message="Marked 10 notifications as read",
    )

    assert response.processed == 10
    assert response.failed == 2
    assert "10" in response.message


@pytest.mark.unit
def test_bulk_request_max_items():
    ids = [str(uuid.uuid4()) for _ in range(1001)]
    with pytest.raises(ValueError):
        BulkMarkReadRequest(notification_ids=ids)


@pytest.mark.unit
def test_bulk_request_min_items():
    with pytest.raises(ValueError):
        BulkMarkReadRequest(notification_ids=[])
