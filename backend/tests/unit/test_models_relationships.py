import pytest

from app.models.delivery import Delivery
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.models.tenant import Tenant
from app.models.user import User


@pytest.mark.unit
def test_notification_model_fields():
    assert hasattr(Notification, "id")
    assert hasattr(Notification, "receiver_id")
    assert hasattr(Notification, "tenant_id")
    assert hasattr(Notification, "content")
    assert hasattr(Notification, "content_preview")
    assert hasattr(Notification, "severity")
    assert hasattr(Notification, "severity_source")
    assert hasattr(Notification, "status")
    assert hasattr(Notification, "storage_backend")
    assert hasattr(Notification, "storage_key")
    assert hasattr(Notification, "content_size")
    assert hasattr(Notification, "content_normalized")
    assert hasattr(Notification, "received_at")
    assert hasattr(Notification, "source_ip")
    assert hasattr(Notification, "meta")


@pytest.mark.unit
def test_delivery_model_fields():
    assert hasattr(Delivery, "id")
    assert hasattr(Delivery, "tenant_id")
    assert hasattr(Delivery, "notification_id")
    assert hasattr(Delivery, "channel_id")
    assert hasattr(Delivery, "status")


@pytest.mark.unit
def test_receiver_model_fields():
    assert hasattr(Receiver, "id")
    assert hasattr(Receiver, "tenant_id")
    assert hasattr(Receiver, "group_id")
    assert hasattr(Receiver, "slug")
    assert hasattr(Receiver, "name")
    assert hasattr(Receiver, "status")
    assert hasattr(Receiver, "ingestion_module")
    assert hasattr(Receiver, "default_severity")
    assert hasattr(Receiver, "max_body_bytes")
    assert hasattr(Receiver, "rate_limit_per_min")


@pytest.mark.unit
def test_tenant_model_timestamps():
    assert hasattr(Tenant, "created_at")
    assert hasattr(Tenant, "updated_at")


@pytest.mark.unit
def test_user_model_fields():
    assert hasattr(User, "id")
    assert hasattr(User, "tenant_id")
    assert hasattr(User, "email")
    assert hasattr(User, "password_hash")
    assert hasattr(User, "role")
    assert hasattr(User, "status")
    assert hasattr(User, "last_login_at")
    assert hasattr(User, "created_at")
    assert hasattr(User, "updated_at")
