"""GET /stats/summary: conteggi per la home della dashboard (spec 9.5)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db
from app.core.security import AccessClaims
from app.db.types import DeliveryStatus, NotificationStatus
from app.models.delivery import Delivery
from app.models.group import Group
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.schemas.notification import StatsSummaryOut

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummaryOut)
async def stats_summary(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> StatsSummaryOut:
    tenant_id = uuid.UUID(claims.tid)

    total_unread_result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.tenant_id == tenant_id,
            Notification.status == NotificationStatus.UNREAD,
        )
    )
    total_unread = total_unread_result.scalar_one()

    by_severity_result = await session.execute(
        select(Notification.severity, func.count(Notification.id))
        .where(Notification.tenant_id == tenant_id)
        .group_by(Notification.severity)
    )
    by_severity = {severity.value: count for severity, count in by_severity_result.all()}

    by_group_result = await session.execute(
        select(
            Group.id,
            Group.name,
            func.count(Notification.id),
            func.count(Notification.id).filter(Notification.status == NotificationStatus.UNREAD),
        )
        .select_from(Group)
        .join(Receiver, Receiver.group_id == Group.id)
        .join(Notification, Notification.receiver_id == Receiver.id)
        .where(Group.tenant_id == tenant_id)
        .group_by(Group.id, Group.name)
    )
    by_group = [
        {"group_id": str(group_id), "group_name": name, "total": total, "unread_count": unread}
        for group_id, name, total, unread in by_group_result.all()
    ]

    since = datetime.now(UTC) - timedelta(hours=24)
    last_24h_result = await session.execute(
        select(func.count(Notification.id)).where(
            Notification.tenant_id == tenant_id, Notification.received_at >= since
        )
    )
    notifications_last_24h = last_24h_result.scalar_one()

    deliveries_dead_result = await session.execute(
        select(func.count(Delivery.id)).where(
            Delivery.tenant_id == tenant_id, Delivery.status == DeliveryStatus.DEAD
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
