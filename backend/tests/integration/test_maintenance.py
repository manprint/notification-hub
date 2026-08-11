"""Test dei 7 job Celery Beat di manutenzione (spec 11): girano contro
Postgres/Redis/MinIO reali, chiamati direttamente come funzioni (come i test
del worker di delivery)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.crypto import encrypt_secret
from app.db.session import async_session_factory_app, tenant_session
from app.db.sync_session import sync_session_factory
from app.db.types import DeliveryStatus, Severity
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.invitation import Invitation
from app.models.notification import Notification
from app.models.object_deletion import PendingObjectDeletion
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User
from app.services.storage import fetch_object, upload_object
from app.tasks.enqueue import reset_enqueue_function, set_enqueue_function
from app.tasks.maintenance import (
    cleanup_tokens,
    drain_object_deletions,
    purge_deliveries,
    purge_notifications,
    purge_orphan_objects,
    recompute_tenant_usage,
    reconcile_deliveries,
)
from tests.conftest_factories import create_receiver


async def _insert_notification(
    tenant_id: uuid.UUID, receiver_id: uuid.UUID, received_at: datetime, content_size: int = 10
) -> uuid.UUID:
    notification_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            Notification(
                id=notification_id,
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                storage_backend="inline",
                content="x" * content_size,
                storage_key=None,
                content_preview="x" * content_size,
                content_size=content_size,
                content_normalized=False,
                severity=Severity.INFO,
                severity_source="receiver_default",
                status="unread",
                received_at=received_at,
                source_ip=None,
                meta={},
            )
        )
    return notification_id


@pytest.mark.integration
async def test_purge_notifications_rispetta_retention_days(two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    async with async_session_factory_app() as session:
        await session.execute(update(Tenant).where(Tenant.id == tenant_id).values(retention_days=7))
        await session.commit()

    old_id = await _insert_notification(
        tenant_id, receiver_id, datetime.now(UTC) - timedelta(days=10)
    )
    fresh_id = await _insert_notification(
        tenant_id, receiver_id, datetime.now(UTC) - timedelta(days=1)
    )

    purge_notifications()

    async with tenant_session(tenant_id) as session:
        assert (await session.get(Notification, old_id)) is None
        assert (await session.get(Notification, fresh_id)) is not None


@pytest.mark.integration
async def test_purge_notifications_reimposta_il_tenant_fra_batch(two_tenants, monkeypatch):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    async with async_session_factory_app() as session:
        await session.execute(update(Tenant).where(Tenant.id == tenant_id).values(retention_days=7))
        await session.commit()

    old_ids = [
        await _insert_notification(tenant_id, receiver_id, datetime.now(UTC) - timedelta(days=10))
        for _ in range(3)
    ]
    monkeypatch.setattr("app.tasks.maintenance.PURGE_BATCH_SIZE", 2)

    purge_notifications()

    async with tenant_session(tenant_id) as session:
        for notification_id in old_ids:
            assert await session.get(Notification, notification_id) is None


@pytest.mark.integration
async def test_purge_deliveries_elimina_sent_vecchie_non_tocca_dead(two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    notification_id = await _insert_notification(tenant_id, receiver_id, datetime.now(UTC))

    channel_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name="Slack #ops",
                type="slack",
                webhook_url=encrypt_secret("https://hooks.slack.com/services/T/B/X"),
                enabled=True,
            )
        )
        await session.flush()

    old_sent_id, fresh_sent_id, dead_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add_all(
            [
                Delivery(
                    id=old_sent_id,
                    tenant_id=tenant_id,
                    notification_id=notification_id,
                    channel_id=channel_id,
                    status=DeliveryStatus.SENT,
                    attempts=0,
                    next_attempt_at=datetime.now(UTC),
                    sent_at=datetime.now(UTC) - timedelta(days=31),
                ),
            ]
        )
        await session.flush()

    # notification_id+channel_id ha un unique constraint: le altre due delivery
    # servono canali/notifiche proprie per evitare la violazione.
    channel_id_2 = uuid.uuid4()
    channel_id_3 = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add_all(
            [
                DeliveryChannel(
                    id=channel_id_2,
                    tenant_id=tenant_id,
                    name="Slack #ops-2",
                    type="slack",
                    webhook_url=encrypt_secret("https://hooks.slack.com/services/T/B/Y"),
                    enabled=True,
                ),
                DeliveryChannel(
                    id=channel_id_3,
                    tenant_id=tenant_id,
                    name="Slack #ops-3",
                    type="slack",
                    webhook_url=encrypt_secret("https://hooks.slack.com/services/T/B/Z"),
                    enabled=True,
                ),
            ]
        )
        await session.flush()

    async with tenant_session(tenant_id) as session:
        session.add_all(
            [
                Delivery(
                    id=fresh_sent_id,
                    tenant_id=tenant_id,
                    notification_id=notification_id,
                    channel_id=channel_id_2,
                    status=DeliveryStatus.SENT,
                    attempts=0,
                    next_attempt_at=datetime.now(UTC),
                    sent_at=datetime.now(UTC) - timedelta(days=1),
                ),
                Delivery(
                    id=dead_id,
                    tenant_id=tenant_id,
                    notification_id=notification_id,
                    channel_id=channel_id_3,
                    status=DeliveryStatus.DEAD,
                    attempts=5,
                    next_attempt_at=datetime.now(UTC) - timedelta(days=60),
                ),
            ]
        )
        await session.flush()

    purge_deliveries()

    async with tenant_session(tenant_id) as session:
        assert (await session.get(Delivery, old_sent_id)) is None
        assert (await session.get(Delivery, fresh_sent_id)) is not None
        assert (await session.get(Delivery, dead_id)) is not None


@pytest.mark.integration
async def test_cleanup_tokens_elimina_scaduti_e_revocati(two_tenants):
    tenant_id, _ = two_tenants
    email = f"cleanup-{uuid.uuid4().hex[:8]}@test.com"
    async with tenant_session(tenant_id) as session:
        user = User(
            tenant_id=tenant_id,
            email=email,
            password_hash="hash",  # noqa: S106
            role="member",
            status="active",
        )
        session.add(user)
        await session.flush()
        user_id = user.id

    now = datetime.now(UTC)
    expired_id, revoked_id, valid_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add_all(
            [
                RefreshToken(
                    id=expired_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    token_hash=f"hash-{expired_id}",
                    jti=str(uuid.uuid4()),
                    family_id=uuid.uuid4(),
                    expires_at=now - timedelta(days=1),
                ),
                RefreshToken(
                    id=revoked_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    token_hash=f"hash-{revoked_id}",
                    jti=str(uuid.uuid4()),
                    family_id=uuid.uuid4(),
                    expires_at=now + timedelta(days=30),
                    revoked_at=now,
                ),
                RefreshToken(
                    id=valid_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    token_hash=f"hash-{valid_id}",
                    jti=str(uuid.uuid4()),
                    family_id=uuid.uuid4(),
                    expires_at=now + timedelta(days=30),
                ),
            ]
        )
        await session.flush()

    expired_inv_id, valid_inv_id = uuid.uuid4(), uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add_all(
            [
                Invitation(
                    id=expired_inv_id,
                    tenant_id=tenant_id,
                    email=f"invite-old-{uuid.uuid4().hex[:8]}@test.com",
                    role="member",
                    token_hash=f"tok-{expired_inv_id}",
                    expires_at=now - timedelta(days=1),
                    invited_by=user_id,
                ),
                Invitation(
                    id=valid_inv_id,
                    tenant_id=tenant_id,
                    email=f"invite-new-{uuid.uuid4().hex[:8]}@test.com",
                    role="member",
                    token_hash=f"tok-{valid_inv_id}",
                    expires_at=now + timedelta(days=7),
                    invited_by=user_id,
                ),
            ]
        )
        await session.flush()

    cleanup_tokens()

    async with tenant_session(tenant_id) as session:
        assert (await session.get(RefreshToken, expired_id)) is None
        assert (await session.get(RefreshToken, revoked_id)) is None
        assert (await session.get(RefreshToken, valid_id)) is not None
        assert (await session.get(Invitation, expired_inv_id)) is None
        assert (await session.get(Invitation, valid_inv_id)) is not None


@pytest.mark.integration
async def test_reconcile_deliveries_ripesca_pending_scadute_e_sending_bloccate(two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    notification_id = await _insert_notification(tenant_id, receiver_id, datetime.now(UTC))

    channel_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name="Slack #ops",
                type="slack",
                webhook_url=encrypt_secret("https://hooks.slack.com/services/T/B/X"),
                enabled=True,
            )
        )
        await session.flush()

    channel_id_2, disabled_channel_id = uuid.uuid4(), uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add_all(
            [
                DeliveryChannel(
                    id=channel_id_2,
                    tenant_id=tenant_id,
                    name="Slack #ops-2",
                    type="slack",
                    webhook_url=encrypt_secret("https://hooks.slack.com/services/T/B/Y"),
                    enabled=True,
                ),
                DeliveryChannel(
                    id=disabled_channel_id,
                    tenant_id=tenant_id,
                    name="Slack disabilitato",
                    type="slack",
                    webhook_url=encrypt_secret("https://hooks.slack.com/services/T/B/Z"),
                    enabled=False,
                ),
            ]
        )
        await session.flush()

    now = datetime.now(UTC)
    due_pending_id, stuck_sending_id, disabled_pending_id = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )
    async with tenant_session(tenant_id) as session:
        session.add_all(
            [
                Delivery(
                    id=due_pending_id,
                    tenant_id=tenant_id,
                    notification_id=notification_id,
                    channel_id=channel_id,
                    status=DeliveryStatus.PENDING,
                    attempts=0,
                    next_attempt_at=now - timedelta(minutes=1),
                ),
                Delivery(
                    id=stuck_sending_id,
                    tenant_id=tenant_id,
                    notification_id=notification_id,
                    channel_id=channel_id_2,
                    status=DeliveryStatus.SENDING,
                    attempts=0,
                    next_attempt_at=now,
                    locked_at=now - timedelta(minutes=15),
                ),
                Delivery(
                    id=disabled_pending_id,
                    tenant_id=tenant_id,
                    notification_id=notification_id,
                    channel_id=disabled_channel_id,
                    status=DeliveryStatus.PENDING,
                    attempts=0,
                    next_attempt_at=now - timedelta(minutes=1),
                ),
            ]
        )
        await session.flush()

    requeued: list[tuple[str, str]] = []
    set_enqueue_function(lambda delivery_id, tid: requeued.append((delivery_id, tid)))
    try:
        reconcile_deliveries()
    finally:
        reset_enqueue_function()

    requeued_ids = {r[0] for r in requeued}
    assert str(due_pending_id) in requeued_ids
    assert str(stuck_sending_id) in requeued_ids
    assert str(disabled_pending_id) in requeued_ids

    async with tenant_session(tenant_id) as session:
        stuck = await session.get(Delivery, stuck_sending_id)
        assert stuck.status == DeliveryStatus.FAILED
        assert stuck.locked_at is None


@pytest.mark.integration
async def test_drain_object_deletions_cancella_oggetto_da_minio_e_riga(two_tenants):
    tenant_id, _ = two_tenants
    storage_key = f"{tenant_id}/maintenance-test/{uuid.uuid4()}.txt"
    await upload_object(storage_key, b"corpo di test da eliminare")

    row_id = uuid.uuid4()
    with sync_session_factory() as session:
        session.add(
            PendingObjectDeletion(
                id=row_id,
                storage_key=storage_key,
                enqueued_at=datetime.now(UTC),
                attempts=0,
            )
        )
        session.commit()

    drain_object_deletions()

    with sync_session_factory() as session:
        assert session.get(PendingObjectDeletion, row_id) is None

    with pytest.raises(Exception):  # noqa: B017
        await fetch_object(storage_key)


@pytest.mark.integration
async def test_purge_orphan_objects_rispetta_finestra_24h(two_tenants, monkeypatch):
    tenant_id, _ = two_tenants
    orphan_key = f"{tenant_id}/orphan-test/{uuid.uuid4()}.txt"
    await upload_object(orphan_key, b"oggetto orfano di test")

    # Appena caricato: piu recente della finestra di 24h, non deve essere toccato.
    purge_orphan_objects()
    body = await fetch_object(orphan_key)
    assert body == b"oggetto orfano di test"

    # Sposta avanti "adesso" di 25h: l'oggetto ricade fuori dalla finestra e va
    # eliminato, dato che la sua chiave non compare in nessuna notifications.storage_key.
    import app.tasks.maintenance as maintenance_module

    real_now = datetime.now(UTC)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return real_now + timedelta(hours=25)

    monkeypatch.setattr(maintenance_module, "datetime", _FakeDateTime)

    purge_orphan_objects()

    with pytest.raises(Exception):  # noqa: B017
        await fetch_object(orphan_key)


@pytest.mark.integration
async def test_recompute_tenant_usage_aggiorna_la_gauge(two_tenants):
    from app.core.metrics import tenant_storage_bytes

    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    await _insert_notification(tenant_id, receiver_id, datetime.now(UTC), content_size=100)
    await _insert_notification(tenant_id, receiver_id, datetime.now(UTC), content_size=250)

    async with tenant_session(tenant_id) as session:
        total = (
            (
                await session.execute(
                    select(Notification.content_size).where(Notification.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        )
    expected = sum(total)

    recompute_tenant_usage()

    value = tenant_storage_bytes.labels(tenant_id=str(tenant_id))._value.get()
    assert value == expected
