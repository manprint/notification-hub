import uuid

import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ingest_notification_success(api_client, two_tenants, owner_conn):
    """POST /ingestion creates notification via API key."""
    from app.db.session import tenant_session
    from app.models.api_key import ApiKey
    from app.models.receiver import Receiver

    tenant_a_id, _ = two_tenants

    async with tenant_session(tenant_a_id) as session:
        receiver = Receiver(
            id=uuid.uuid4(),
            tenant_id=tenant_a_id,
            group_id=uuid.uuid4(),
            slug="test-receiver",
        )
        session.add(receiver)
        await session.flush()

        api_key = ApiKey(
            id=uuid.uuid4(),
            receiver_id=receiver.id,
            key_hash="test_hash",
            label="Test Key",
        )
        session.add(api_key)
        await session.commit()

    response = await api_client.post(
        "/api/v1/ingestion",
        json={
            "title": "Test Alert",
            "body": "Test notification body",
            "severity": "info",
        },
        headers={"Authorization": "Bearer test_hash"},
    )

    assert response.status_code == 202
    data = response.json()
    assert "notification_id" in data
    assert data["status"] == "enqueued"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ingest_notification_invalid_api_key(api_client, two_tenants):
    """POST /ingestion fails with invalid API key."""
    response = await api_client.post(
        "/api/v1/ingestion",
        json={
            "title": "Test Alert",
            "body": "Test notification body",
            "severity": "info",
        },
        headers={"Authorization": "Bearer invalid_key"},
    )

    assert response.status_code == 401


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ingest_notification_by_receiver_slug(api_client, two_tenants):
    """POST /ingestion/{receiver_slug} creates notification."""
    from app.db.session import tenant_session
    from app.models.api_key import ApiKey
    from app.models.receiver import Receiver

    tenant_a_id, _ = two_tenants

    async with tenant_session(tenant_a_id) as session:
        receiver = Receiver(
            id=uuid.uuid4(),
            tenant_id=tenant_a_id,
            group_id=uuid.uuid4(),
            slug="webhook-receiver",
        )
        session.add(receiver)
        await session.flush()

        api_key = ApiKey(
            id=uuid.uuid4(),
            receiver_id=receiver.id,
            key_hash="webhook_hash",
            label="Webhook Key",
        )
        session.add(api_key)
        await session.commit()

    response = await api_client.post(
        "/api/v1/ingestion/webhook-receiver",
        json={
            "title": "Webhook Alert",
            "body": "From webhook",
            "severity": "warning",
        },
        headers={"Authorization": "Bearer webhook_hash"},
    )

    assert response.status_code == 202
