import pytest
from sqlalchemy import LargeBinary, UniqueConstraint

from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.object_deletion import PendingObjectDeletion


@pytest.mark.unit
def test_webhook_url_e_binario():
    webhook_col = DeliveryChannel.__table__.c.webhook_url
    assert isinstance(webhook_col.type, LargeBinary)


@pytest.mark.unit
def test_unicita_delivery():
    unique_constraints = [
        c
        for c in Delivery.__table__.constraints
        if isinstance(c, UniqueConstraint)
        and tuple(c.columns.keys()) == ("notification_id", "channel_id")
    ]
    assert len(unique_constraints) == 1


@pytest.mark.unit
def test_pending_object_deletions_senza_tenant():
    assert "tenant_id" not in PendingObjectDeletion.__table__.columns
