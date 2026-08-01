from fastapi import APIRouter, Depends, Header
from sqlalchemy import select

from app.api.deps import receiver_auth
from app.core.errors import PROBLEM_TYPES, Problem
from app.db.session import tenant_session
from app.models.receiver import Receiver
from app.schemas.ingestion import NotificationIngest, NotificationIngestResponse
from app.services.ingestion import ReceiverAuth, create_notification
from app.services.ratelimit import sliding_window_hit

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("", response_model=NotificationIngestResponse, status_code=202)
async def ingest_notification(
    body: NotificationIngest,
    auth: ReceiverAuth = Depends(receiver_auth),  # noqa: B008
) -> NotificationIngestResponse:
    if len(body.body.encode()) > auth.max_body_bytes:
        raise Problem(
            status=413,
            type=PROBLEM_TYPES["payload_too_large"],
            title="Payload Too Large",
            detail=f"Notification body exceeds {auth.max_body_bytes} bytes.",
        )

    rate_limit_key = f"receiver_ingest:{auth.receiver_id}"
    rate_limit = await sliding_window_hit(rate_limit_key, auth.rate_limit_per_min, 60)

    if not rate_limit.allowed:
        raise Problem(
            status=429,
            type=PROBLEM_TYPES["rate_limited"],
            title="Too Many Requests",
            detail="Receiver rate limit exceeded.",
        )

    async with tenant_session(auth.tenant_id) as session:
        severity = body.severity or "info"
        notification_id = await create_notification(
            session,
            auth.receiver_id,
            auth.tenant_id,
            body.title,
            body.body,
            severity,
            body.metadata,
        )
        await session.commit()

    return NotificationIngestResponse(notification_id=str(notification_id))


@router.post("/{receiver_slug}", response_model=NotificationIngestResponse, status_code=202)
async def ingest_by_slug(
    receiver_slug: str,
    body: NotificationIngest,
    authorization: str = Header(...),  # noqa: B008
) -> NotificationIngestResponse:
    from app.db.session import auth_session
    from app.services.ingestion import authenticate_receiver

    async with auth_session() as session:
        receiver_result = await session.execute(
            select(Receiver).where(Receiver.slug == receiver_slug)
        )
        receiver = receiver_result.scalar_one_or_none()

        if receiver is None or receiver.status != "active":
            raise Problem(
                status=404,
                type=PROBLEM_TYPES["not_found"],
                title="Not Found",
                detail="Receiver not found.",
            )

    if not authorization.startswith("Bearer "):
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid API key.",
        )

    api_key = authorization[7:]
    auth = await authenticate_receiver(api_key)
    if auth is None or auth.receiver_id != receiver.id:
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid or revoked API key.",
        )

    if len(body.body.encode()) > auth.max_body_bytes:
        raise Problem(
            status=413,
            type=PROBLEM_TYPES["payload_too_large"],
            title="Payload Too Large",
            detail=f"Notification body exceeds {auth.max_body_bytes} bytes.",
        )

    rate_limit_key = f"receiver_ingest:{auth.receiver_id}"
    rate_limit = await sliding_window_hit(rate_limit_key, auth.rate_limit_per_min, 60)

    if not rate_limit.allowed:
        raise Problem(
            status=429,
            type=PROBLEM_TYPES["rate_limited"],
            title="Too Many Requests",
            detail="Receiver rate limit exceeded.",
        )

    async with tenant_session(auth.tenant_id) as session:
        severity = body.severity or "info"
        notification_id = await create_notification(
            session,
            auth.receiver_id,
            auth.tenant_id,
            body.title,
            body.body,
            severity,
            body.metadata,
        )
        await session.commit()

    return NotificationIngestResponse(notification_id=str(notification_id))
