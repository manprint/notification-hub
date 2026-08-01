import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.models.channel import DeliveryChannel
from app.schemas.delivery import DeliveryChannelCreate, DeliveryChannelOut

router = APIRouter(prefix="/delivery", tags=["delivery"])


@router.get("/channels", response_model=list[DeliveryChannelOut])
async def list_channels(  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[DeliveryChannelOut]:
    result = await session.execute(
        select(DeliveryChannel).where(DeliveryChannel.tenant_id == uuid.UUID(claims.tid))
    )
    channels = result.scalars().all()
    return [DeliveryChannelOut.model_validate(ch) for ch in channels]


@router.post("/channels", response_model=DeliveryChannelOut, status_code=201)
async def create_channel(  # noqa: B008
    body: DeliveryChannelCreate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelOut:
    channel = DeliveryChannel(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID(claims.tid),
        name=body.name,
        type=body.type,
        webhook_url=body.webhook_url,
        enabled=body.enabled,
    )
    session.add(channel)
    await session.flush()
    return DeliveryChannelOut.model_validate(channel)


@router.get("/channels/{channel_id}", response_model=DeliveryChannelOut)
async def get_channel(  # noqa: B008
    channel_id: str,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelOut:
    result = await session.execute(
        select(DeliveryChannel).where(
            DeliveryChannel.id == uuid.UUID(channel_id),
            DeliveryChannel.tenant_id == uuid.UUID(claims.tid),
        )
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Delivery channel not found.",
        )
    return DeliveryChannelOut.model_validate(channel)
