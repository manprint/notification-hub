"""Enforcement delle quote per tenant (spec 4.1, F7): colonne presenti da F1,
applicate qui. Nessuna colonna nuova rispetto allo schema della spec: l'uso
corrente e calcolato dal vivo, non cacciato in un campo non previsto."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PROBLEM_TYPES, Problem
from app.models.notification import Notification
from app.models.tenant import Tenant


async def enforce_tenant_quotas(
    session: AsyncSession, tenant_id: uuid.UUID, incoming_bytes: int
) -> None:
    """Solleva 429 se il tenant ha superato max_notifications_per_day o
    max_storage_bytes (NULL = illimitato, spec 4.1). Va chiamato PRIMA di
    scrivere la nuova Notification."""
    # Prima una lettura senza lock, solo per sapere se c'e' una quota da
    # applicare: `FOR UPDATE` sulla riga del tenant serializza TUTTE le
    # ingestion di quel tenant per la durata della transazione, e prenderlo
    # anche quando entrambe le quote sono NULL (il default: illimitate) rendeva
    # sequenziale l'intera ingestion senza che ci fosse niente da proteggere.
    limits = (
        await session.execute(
            select(Tenant.max_notifications_per_day, Tenant.max_storage_bytes).where(
                Tenant.id == tenant_id
            )
        )
    ).one()
    if limits.max_notifications_per_day is None and limits.max_storage_bytes is None:
        return

    # Con almeno una quota configurata il lock serve: il controllo e l'INSERT
    # della notifica avvengono nella stessa transazione e senza serializzare
    # due richieste concorrenti potevano entrambe osservare quota disponibile
    # e superarla.
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update()
    )
    tenant = tenant_result.scalar_one()

    if tenant.max_notifications_per_day is not None:
        since = datetime.now(UTC) - timedelta(days=1)
        count_result = await session.execute(
            select(func.count(Notification.id)).where(
                Notification.tenant_id == tenant_id, Notification.received_at >= since
            )
        )
        if count_result.scalar_one() >= tenant.max_notifications_per_day:
            raise Problem(
                status=429,
                type=PROBLEM_TYPES["quota_exceeded"],
                title="Too Many Requests",
                detail="Daily notification quota exceeded for this tenant.",
            )

    if tenant.max_storage_bytes is not None:
        used_result = await session.execute(
            select(func.coalesce(func.sum(Notification.content_size), 0)).where(
                Notification.tenant_id == tenant_id
            )
        )
        used = used_result.scalar_one()
        if used + incoming_bytes > tenant.max_storage_bytes:
            raise Problem(
                status=429,
                type=PROBLEM_TYPES["quota_exceeded"],
                title="Too Many Requests",
                detail="Storage quota exceeded for this tenant.",
            )
