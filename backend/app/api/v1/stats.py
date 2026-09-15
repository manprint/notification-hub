"""GET /stats/summary: conteggi per la home della dashboard (spec 9.5)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db
from app.core.security import AccessClaims
from app.db.types import DeliveryStatus, NotificationStatus
from app.models.delivery import Delivery
from app.models.group import Group
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.schemas.notification import GroupStatsOut, ReceiverStatsOut, StatsSummaryOut
from app.services.authz import accessible_group_ids

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummaryOut)
async def stats_summary(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> StatsSummaryOut:
    tenant_id = uuid.UUID(claims.tid)

    # member e viewer vedono i conteggi dei soli gruppi a cui sono associati:
    # la home mostrava invece i totali dell'intero tenant a chiunque.
    allowed = await accessible_group_ids(session, claims)
    if allowed is not None and not allowed:
        return StatsSummaryOut(
            total_unread=0,
            by_severity={},
            by_group=[],
            notifications_last_24h=0,
            deliveries_dead=0,
        )

    scope: list = [Notification.tenant_id == tenant_id]
    group_scope: list = [Group.tenant_id == tenant_id]
    delivery_scope: list = [Delivery.tenant_id == tenant_id]
    if allowed is not None:
        visible_receivers = select(Receiver.id).where(
            Receiver.tenant_id == tenant_id, Receiver.group_id.in_(allowed)
        )
        scope.append(Notification.receiver_id.in_(visible_receivers))
        group_scope.append(Group.id.in_(allowed))
        delivery_scope.append(
            Delivery.notification_id.in_(
                select(Notification.id).where(
                    Notification.tenant_id == tenant_id,
                    Notification.receiver_id.in_(visible_receivers),
                )
            )
        )

    total_unread_result = await session.execute(
        select(func.count(Notification.id)).where(
            *scope, Notification.status == NotificationStatus.UNREAD
        )
    )
    total_unread = total_unread_result.scalar_one()

    by_severity_result = await session.execute(
        select(Notification.severity, func.count(Notification.id))
        .where(*scope)
        .group_by(Notification.severity)
    )
    by_severity = {severity.value: count for severity, count in by_severity_result.all()}

    # Granularita' gruppo -> receiver: il riepilogo dice anche QUALE receiver del
    # gruppo ha prodotto quelle notifiche. OUTER JOIN su entrambi i lati perche'
    # un receiver che non ha mai scritto (total=0) e' un'informazione, non una
    # riga da nascondere; per lo stesso motivo compare anche un gruppo ancora
    # senza receiver. Il conteggio su Notification.id resta 0 sulle righe senza
    # corrispondenza, che e' esattamente quel che serve.
    by_group_result = await session.execute(
        select(
            Group.id,
            Group.name,
            Receiver.id,
            Receiver.name,
            Receiver.status,
            func.count(Notification.id),
            func.count(Notification.id).filter(Notification.status == NotificationStatus.UNREAD),
        )
        .select_from(Group)
        .outerjoin(
            Receiver,
            and_(Receiver.group_id == Group.id, Receiver.tenant_id == tenant_id),
        )
        .outerjoin(
            Notification,
            and_(
                Notification.receiver_id == Receiver.id,
                Notification.tenant_id == tenant_id,
            ),
        )
        .where(*group_scope)
        .group_by(Group.id, Group.name, Receiver.id, Receiver.name, Receiver.status)
        .order_by(Group.name, Receiver.name)
    )

    by_group_index: dict[uuid.UUID, GroupStatsOut] = {}
    for (
        group_id,
        group_name,
        receiver_id,
        receiver_name,
        receiver_status,
        total,
        unread,
    ) in by_group_result.all():
        group_row = by_group_index.get(group_id)
        if group_row is None:
            group_row = GroupStatsOut(
                group_id=str(group_id),
                group_name=group_name,
                total=0,
                unread_count=0,
                receivers=[],
            )
            by_group_index[group_id] = group_row
        if receiver_id is None:
            # Gruppo senza receiver: la riga esiste, ma non c'e' nessun receiver
            # da elencarci sotto.
            continue
        group_row.receivers.append(
            ReceiverStatsOut(
                receiver_id=str(receiver_id),
                receiver_name=receiver_name,
                status=receiver_status.value
                if hasattr(receiver_status, "value")
                else str(receiver_status),
                total=total,
                unread_count=unread,
            )
        )
        # Il totale del gruppo e' la somma dei suoi receiver: una sola scansione
        # invece di una seconda query di aggregazione.
        group_row.total += total
        group_row.unread_count += unread
    by_group = list(by_group_index.values())

    since = datetime.now(UTC) - timedelta(hours=24)
    last_24h_result = await session.execute(
        select(func.count(Notification.id)).where(*scope, Notification.received_at >= since)
    )
    notifications_last_24h = last_24h_result.scalar_one()

    deliveries_dead_result = await session.execute(
        select(func.count(Delivery.id)).where(
            *delivery_scope, Delivery.status == DeliveryStatus.DEAD
        )
    )
    deliveries_dead = deliveries_dead_result.scalar_one()

    return StatsSummaryOut(
        total_unread=total_unread,
        by_severity=by_severity,
        by_group=by_group,
        notifications_last_24h=notifications_last_24h,
        deliveries_dead=deliveries_dead,
    )
