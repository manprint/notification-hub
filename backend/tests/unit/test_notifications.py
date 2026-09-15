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
        verified=False,
        received_at=now,
    )
    assert item.status == "unread"
    assert item.severity == "info"
    assert item.verified is False


@pytest.mark.unit
def test_mark_status_schema():
    body = MarkStatusIn(status="read")
    assert body.status == "read"


@pytest.mark.unit
def test_mark_status_accepts_verified_only():
    body = MarkStatusIn(verified=True)
    assert body.verified is True
    assert body.status is None


@pytest.mark.unit
def test_mark_status_rejects_empty_body():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MarkStatusIn()


@pytest.mark.unit
def test_bulk_read_schema_accepts_from_alias():
    body = BulkReadIn.model_validate(
        {"group_id": str(uuid.uuid4()), "from": "2026-01-01T00:00:00Z"}
    )
    assert body.group_id is not None
    assert body.from_ is not None


@pytest.mark.unit
def test_search_condition_usa_l_espressione_indicizzata():
    """La query deve scrivere l'espressione esattamente come la indicizza la
    migrazione 0015: una forma diversa costerebbe un sequential scan."""
    from sqlalchemy.dialects import postgresql

    from app.api.v1.notifications import search_condition

    sql = str(search_condition("errore").compile(dialect=postgresql.dialect())).lower()
    assert "coalesce(notifications.content, notifications.content_preview)" in sql
    assert "ilike" in sql


@pytest.mark.unit
def test_search_condition_neutralizza_i_metacaratteri_like():
    """`%` e `_` digitati nella casella di ricerca sono testo, non jolly."""
    from sqlalchemy.dialects import postgresql

    from app.api.v1.notifications import search_condition

    compiled = search_condition("50%_a\\b").compile(dialect=postgresql.dialect())
    pattern = next(
        value
        for value in compiled.params.values()
        if isinstance(value, str) and value.startswith("%") and len(value) > 1
    )
    assert pattern == "%50\\%\\_a\\\\b%"
