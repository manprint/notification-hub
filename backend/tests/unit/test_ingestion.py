import pytest

from app.schemas.ingestion import NotificationIngest, NotificationIngestResponse


@pytest.mark.unit
def test_notification_ingest_valid():
    payload = NotificationIngest(title="Test", body="Body")
    assert payload.title == "Test"
    assert payload.body == "Body"
    assert payload.severity is None
    assert payload.metadata is None


@pytest.mark.unit
def test_notification_ingest_with_severity():
    payload = NotificationIngest(title="Test", body="Body", severity="error")
    assert payload.severity == "error"


@pytest.mark.unit
def test_notification_ingest_with_metadata():
    metadata = {"key": "value"}
    payload = NotificationIngest(title="Test", body="Body", metadata=metadata)
    assert payload.metadata == metadata


@pytest.mark.unit
def test_notification_ingest_response():
    response = NotificationIngestResponse(notification_id="123e4567-e89b-12d3-a456-426614174000")
    assert response.notification_id == "123e4567-e89b-12d3-a456-426614174000"
    assert response.status == "enqueued"


@pytest.mark.unit
def test_notification_ingest_title_empty_fails():
    with pytest.raises(ValueError):
        NotificationIngest(title="", body="Body")


@pytest.mark.unit
def test_notification_ingest_large_body():
    large_body = "x" * 1048576
    payload = NotificationIngest(title="Test", body=large_body)
    assert len(payload.body) == 1048576
