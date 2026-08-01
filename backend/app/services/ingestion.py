import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token
from app.db.session import auth_session
from app.models.api_key import ApiKey
from app.models.receiver import Receiver


@dataclass
class ReceiverAuth:
    receiver_id: uuid.UUID
    tenant_id: uuid.UUID
    max_body_bytes: int
    rate_limit_per_min: int


async def authenticate_receiver(api_key_plain: str) -> ReceiverAuth | None:
    """Verify API key and return receiver context."""
    api_key_hash = hash_token(api_key_plain)

    async with auth_session() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.key_hash == api_key_hash, ApiKey.revoked_at.is_(None))
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            return None

        receiver_result = await session.execute(
            select(Receiver).where(Receiver.id == api_key.receiver_id)
        )
        receiver = receiver_result.scalar_one_or_none()
        if receiver is None or receiver.status != "active":
            return None

        return ReceiverAuth(
            receiver_id=receiver.id,
            tenant_id=receiver.tenant_id,
            max_body_bytes=receiver.max_body_bytes,
            rate_limit_per_min=receiver.rate_limit_per_min,
        )


async def create_notification(
    session: AsyncSession,
    receiver_id: uuid.UUID,
    tenant_id: uuid.UUID,
    title: str,
    body: str,
    severity: str,
    metadata: dict | None = None,
) -> uuid.UUID:
    """Create notification in database."""
    from app.models.notification import Notification

    notification = Notification(
        id=uuid.uuid4(),
        receiver_id=receiver_id,
        tenant_id=tenant_id,
        title=title,
        body=body,
        severity=severity,
        meta=metadata or {},
        status="unread",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(notification)
    await session.flush()
    return notification.id
