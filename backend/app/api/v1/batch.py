import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db
from app.core.security import AccessClaims
from app.db.types import NotificationStatus
from app.models.notification import Notification
from app.schemas.batch import (
    BulkArchiveRequest,
    BulkDeleteRequest,
    BulkMarkReadRequest,
    BulkMarkUnreadRequest,
    BulkOperationResponse,
)

router = APIRouter(prefix="/batch", tags=["batch"])


@router.post("/mark-read", response_model=BulkOperationResponse)
async def bulk_mark_read(
    body: BulkMarkReadRequest,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> BulkOperationResponse:
    """Mark multiple notifications as read."""
    tenant_id = uuid.UUID(claims.tid)
    notification_ids = [uuid.UUID(nid) for nid in body.notification_ids]

    to_update = await session.execute(
        select(Notification).where(
            Notification.id.in_(notification_ids),
            Notification.tenant_id == tenant_id,
        )
    )
    notifications = to_update.scalars().all()
    processed = len(notifications)

    await session.execute(
        update(Notification)
        .where(
            Notification.id.in_(notification_ids),
            Notification.tenant_id == tenant_id,
        )
        .values(status=NotificationStatus.READ)
    )

    failed = len(notification_ids) - processed

    await session.commit()

    return BulkOperationResponse(
        processed=processed,
        failed=failed,
        message=f"Marked {processed} notifications as read",
    )


@router.post("/mark-unread", response_model=BulkOperationResponse)
async def bulk_mark_unread(
    body: BulkMarkUnreadRequest,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> BulkOperationResponse:
    """Mark multiple notifications as unread."""
    tenant_id = uuid.UUID(claims.tid)
    notification_ids = [uuid.UUID(nid) for nid in body.notification_ids]

    to_update = await session.execute(
        select(Notification).where(
            Notification.id.in_(notification_ids),
            Notification.tenant_id == tenant_id,
        )
    )
    notifications = to_update.scalars().all()
    processed = len(notifications)

    await session.execute(
        update(Notification)
        .where(
            Notification.id.in_(notification_ids),
            Notification.tenant_id == tenant_id,
        )
        .values(status=NotificationStatus.UNREAD, archived_at=None)
    )

    failed = len(notification_ids) - processed

    await session.commit()

    return BulkOperationResponse(
        processed=processed,
        failed=failed,
        message=f"Marked {processed} notifications as unread",
    )


@router.post("/archive", response_model=BulkOperationResponse)
async def bulk_archive(
    body: BulkArchiveRequest,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> BulkOperationResponse:
    """Archive multiple notifications."""
    tenant_id = uuid.UUID(claims.tid)
    notification_ids = [uuid.UUID(nid) for nid in body.notification_ids]

    to_update = await session.execute(
        select(Notification).where(
            Notification.id.in_(notification_ids),
            Notification.tenant_id == tenant_id,
        )
    )
    notifications = to_update.scalars().all()
    processed = len(notifications)

    await session.execute(
        update(Notification)
        .where(
            Notification.id.in_(notification_ids),
            Notification.tenant_id == tenant_id,
        )
        .values(archived_at=datetime.now(UTC))
    )

    failed = len(notification_ids) - processed

    await session.commit()

    return BulkOperationResponse(
        processed=processed,
        failed=failed,
        message=f"Archived {processed} notifications",
    )


@router.post("/delete", response_model=BulkOperationResponse)
async def bulk_delete(
    body: BulkDeleteRequest,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> BulkOperationResponse:
    """Hard delete multiple notifications."""
    tenant_id = uuid.UUID(claims.tid)
    notification_ids = [uuid.UUID(nid) for nid in body.notification_ids]

    result = await session.execute(
        select(Notification).where(
            Notification.id.in_(notification_ids),
            Notification.tenant_id == tenant_id,
        )
    )
    notifications = result.scalars().all()

    for notification in notifications:
        await session.delete(notification)

    processed = len(notifications)
    failed = len(notification_ids) - processed

    await session.commit()

    return BulkOperationResponse(
        processed=processed,
        failed=failed,
        message=f"Deleted {processed} notifications",
    )
