import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.db.types import NotificationStatus
from app.models.notification import Notification
from app.schemas.notification import (
    ArchiveRequest,
    MarkReadRequest,
    MarkUnreadRequest,
    NotificationListOut,
    NotificationOut,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    status: NotificationStatus | None = Query(None),  # noqa: B008
    receiver_id: str | None = Query(None),  # noqa: B008
    skip: int = Query(0, ge=0),  # noqa: B008
    limit: int = Query(20, ge=1, le=100),  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> NotificationListOut:
    tenant_id = uuid.UUID(claims.tid)

    where_clauses = [
        Notification.tenant_id == tenant_id,
        Notification.archived_at.is_(None),
    ]

    if status:
        where_clauses.append(Notification.status == status)

    if receiver_id:
        where_clauses.append(Notification.receiver_id == uuid.UUID(receiver_id))

    count_result = await session.execute(select(Notification).where(*where_clauses))
    total = len(count_result.scalars().all())

    result = await session.execute(
        select(Notification)
        .where(*where_clauses)
        .order_by(Notification.received_at.desc())
        .offset(skip)
        .limit(limit)
    )
    notifications = result.scalars().all()

    unread_result = await session.execute(
        select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.status == NotificationStatus.UNREAD,
            Notification.archived_at.is_(None),
        )
    )
    unread_count = len(unread_result.scalars().all())

    return NotificationListOut(
        notifications=[NotificationOut.model_validate(n) for n in notifications],
        total=total,
        unread_count=unread_count,
    )


@router.get("/{notification_id}", response_model=NotificationOut)
async def get_notification(
    notification_id: str,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> NotificationOut:
    result = await session.execute(
        select(Notification).where(
            Notification.id == uuid.UUID(notification_id),
            Notification.tenant_id == uuid.UUID(claims.tid),
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Notification not found.",
        )
    return NotificationOut.model_validate(notification)


@router.post("/mark-read")
async def mark_read(
    body: MarkReadRequest,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> dict:
    tenant_id = uuid.UUID(claims.tid)

    result = await session.execute(
        select(Notification).where(
            Notification.id.in_([uuid.UUID(nid) for nid in body.notification_ids]),
            Notification.tenant_id == tenant_id,
        )
    )
    notifications = result.scalars().all()

    for notification in notifications:
        notification.status = NotificationStatus.READ

    await session.flush()
    return {"marked_read": len(notifications)}


@router.post("/mark-unread")
async def mark_unread(
    body: MarkUnreadRequest,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> dict:
    tenant_id = uuid.UUID(claims.tid)

    result = await session.execute(
        select(Notification).where(
            Notification.id.in_([uuid.UUID(nid) for nid in body.notification_ids]),
            Notification.tenant_id == tenant_id,
        )
    )
    notifications = result.scalars().all()

    for notification in notifications:
        notification.status = NotificationStatus.UNREAD
        notification.archived_at = None

    await session.flush()
    return {"marked_unread": len(notifications)}


@router.post("/archive")
async def archive(
    body: ArchiveRequest,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> dict:
    tenant_id = uuid.UUID(claims.tid)

    result = await session.execute(
        select(Notification).where(
            Notification.id.in_([uuid.UUID(nid) for nid in body.notification_ids]),
            Notification.tenant_id == tenant_id,
        )
    )
    notifications = result.scalars().all()

    now = datetime.now(UTC)
    for notification in notifications:
        notification.archived_at = now

    await session.flush()
    return {"archived": len(notifications)}
