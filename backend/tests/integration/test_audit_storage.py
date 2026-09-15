"""Garanzie della tabella di audit sul database reale (spec 9.6): isolamento
per tenant, immutabilita' per l'applicazione, ritenzione propria."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import tenant_session
from app.db.types import AuditOutcome, UserRole
from app.models.audit_event import AuditEvent
from app.models.tenant import Tenant
from app.tasks.maintenance import purge_audit_events


async def _insert_event(
    tenant_id: uuid.UUID,
    occurred_at: datetime,
    action: str = "notification.marked_read",
) -> uuid.UUID:
    event_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            AuditEvent(
                id=event_id,
                tenant_id=tenant_id,
                occurred_at=occurred_at,
                actor_user_id=None,
                actor_email="attore@test.com",
                actor_role=UserRole.OWNER,
                action=action,
                resource_type="notification",
                resource_id=uuid.uuid4(),
                outcome=AuditOutcome.SUCCESS,
            )
        )
    return event_id


@pytest.mark.integration
async def test_rls_isola_gli_eventi_fra_tenant(two_tenants):
    tenant_a, tenant_b = two_tenants
    event_id = await _insert_event(tenant_a, datetime.now(UTC))

    async with tenant_session(tenant_b) as session:
        result = await session.execute(select(AuditEvent).where(AuditEvent.id == event_id))
        assert result.scalar_one_or_none() is None

    async with tenant_session(tenant_a) as session:
        result = await session.execute(select(AuditEvent).where(AuditEvent.id == event_id))
        assert result.scalar_one_or_none() is not None


@pytest.mark.integration
async def test_l_applicazione_non_puo_modificare_un_evento(two_tenants):
    """Append-only per NotifyHub: la GRANT di UPDATE e' revocata (0016). Un
    evento scritto non si corregge, nemmeno per errore di un endpoint futuro."""
    tenant_a, _ = two_tenants
    event_id = await _insert_event(tenant_a, datetime.now(UTC))

    with pytest.raises(Exception, match="permission denied|InsufficientPrivilege"):
        async with tenant_session(tenant_a) as session:
            await session.execute(
                update(AuditEvent).where(AuditEvent.id == event_id).values(action="manomesso")
            )


@pytest.mark.integration
async def test_purge_rispetta_la_ritenzione_dedicata(two_tenants):
    """`audit_retention_days` e' separato da `retention_days`: l'audit deve
    sopravvivere alle notifiche che descrive."""
    tenant_a, _ = two_tenants
    async with tenant_session(tenant_a) as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_a))).scalar_one()
        tenant.audit_retention_days = 30

    now = datetime.now(UTC)
    vecchio = await _insert_event(tenant_a, now - timedelta(days=31))
    recente = await _insert_event(tenant_a, now - timedelta(days=29))

    purge_audit_events()

    async with tenant_session(tenant_a) as session:
        rimasti = (
            (
                await session.execute(
                    select(AuditEvent.id).where(AuditEvent.id.in_([vecchio, recente]))
                )
            )
            .scalars()
            .all()
        )
    assert rimasti == [recente]


@pytest.mark.integration
async def test_ritenzione_nulla_conserva_tutto(two_tenants):
    tenant_a, _ = two_tenants
    async with tenant_session(tenant_a) as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_a))).scalar_one()
        tenant.audit_retention_days = None

    antico = await _insert_event(tenant_a, datetime.now(UTC) - timedelta(days=4000))

    purge_audit_events()

    async with tenant_session(tenant_a) as session:
        result = await session.execute(select(AuditEvent.id).where(AuditEvent.id == antico))
        assert result.scalar_one_or_none() == antico


@pytest.mark.integration
async def test_l_indice_gin_serve_la_ricerca_per_notifica(two_tenants):
    """La ricerca per singola notifica deve trovare anche i bulk-read, che
    portano gli id dentro `context`."""
    tenant_a, _ = two_tenants
    notification_id = uuid.uuid4()
    async with tenant_session(tenant_a) as session:
        session.add(
            AuditEvent(
                tenant_id=tenant_a,
                actor_user_id=None,
                actor_email="attore@test.com",
                actor_role=UserRole.OWNER,
                action="notification.bulk_marked_read",
                resource_type="notification",
                outcome=AuditOutcome.SUCCESS,
                context={"count": 1, "notification_ids": [str(notification_id)]},
            )
        )

    # Stessa espressione dell'endpoint /audit/notification-status: quella che
    # l'indice GIN della migrazione 0016 e' li per servire.
    async with tenant_session(tenant_a) as session:
        result = await session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                cast(AuditEvent.context["notification_ids"], JSONB).op("@>")(
                    func.jsonb_build_array(str(notification_id))
                )
            )
        )
        assert result.scalar_one() == 1
