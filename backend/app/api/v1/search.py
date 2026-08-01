import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db
from app.core.security import AccessClaims
from app.db.types import Severity
from app.models.notification import Notification
from app.schemas.search import (
    NotificationAggregation,
    NotificationSearchFilters,
    NotificationSearchResponse,
    NotificationSearchResult,
)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/notifications", response_model=NotificationSearchResponse)
async def search_notifications(
    filters: NotificationSearchFilters,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> NotificationSearchResponse:
    start_time = time.time()
    tenant_id = uuid.UUID(claims.tid)

    where_clauses = [Notification.tenant_id == tenant_id]

    if not filters.archived:
        where_clauses.append(Notification.archived_at.is_(None))
    else:
        where_clauses.append(Notification.archived_at.isnot(None))

    if filters.query:
        where_clauses.append(
            and_(
                text(
                    "to_tsvector('english', content_preview) @@ plainto_tsquery('english', :query)"
                )
            )
        )

    if filters.severity:
        where_clauses.append(
            Notification.severity.in_(
                [s.value if isinstance(s, Severity) else s for s in filters.severity]
            )
        )

    if filters.status:
        where_clauses.append(Notification.status == filters.status)

    if filters.receiver_id:
        where_clauses.append(Notification.receiver_id == uuid.UUID(filters.receiver_id))

    if filters.received_after:
        where_clauses.append(Notification.received_at >= filters.received_after)

    if filters.received_before:
        where_clauses.append(Notification.received_at <= filters.received_before)

    sort_col = (
        Notification.received_at if filters.sort_by == "received_at" else Notification.severity
    )
    sort_order = sort_col.desc() if filters.sort_order == "desc" else sort_col.asc()

    query = select(Notification).where(*where_clauses).order_by(sort_order)

    count_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await session.execute(query.offset(filters.skip).limit(filters.limit))
    notifications = result.scalars().all()

    took_ms = int((time.time() - start_time) * 1000)

    return NotificationSearchResponse(
        results=[
            NotificationSearchResult(
                id=str(n.id),
                title=n.content_preview[:100],
                content_preview=n.content_preview,
                severity=n.severity,
                status=n.status,
                received_at=n.received_at,
            )
            for n in notifications
        ],
        total=total,
        took_ms=took_ms,
    )


@router.get("/notifications/aggregate", response_model=NotificationAggregation)
async def aggregate_notifications(
    receiver_id: str | None = None,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> NotificationAggregation:
    tenant_id = uuid.UUID(claims.tid)

    where_clauses = [
        Notification.tenant_id == tenant_id,
        Notification.archived_at.is_(None),
    ]

    if receiver_id:
        where_clauses.append(Notification.receiver_id == uuid.UUID(receiver_id))

    severity_result = await session.execute(
        select(Notification.severity, func.count(Notification.id))
        .where(*where_clauses)
        .group_by(Notification.severity)
    )
    severity_counts: dict[str, int] = {str(k): v for k, v in severity_result.all()}

    status_result = await session.execute(
        select(Notification.status, func.count(Notification.id))
        .where(*where_clauses)
        .group_by(Notification.status)
    )
    status_counts: dict[str, int] = {str(k): v for k, v in status_result.all()}

    by_receiver = None
    if not receiver_id:
        receiver_result = await session.execute(
            select(
                Notification.receiver_id,
                func.count(Notification.id),
            )
            .where(*where_clauses)
            .group_by(Notification.receiver_id)
        )
        by_receiver = {str(r[0]): r[1] for r in receiver_result.all()}

    return NotificationAggregation(
        severity=severity_counts,
        status=status_counts,
        by_receiver=by_receiver,
    )
