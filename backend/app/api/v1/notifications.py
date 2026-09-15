"""Consultazione delle notifiche (spec 9.5)."""

import base64
import binascii
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from starlette.responses import StreamingResponse

from app.api.deps import current_claims, db, require_member
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.core.urls import public_base_url
from app.db.types import NotificationStatus, Severity, SeveritySource
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.schemas.notification import (
    LIST_PREVIEW_CHARS,
    BulkReadIn,
    BulkReadOut,
    MarkStatusIn,
    NotificationDetailOut,
    NotificationListItemOut,
    NotificationListOut,
)
from app.services.authz import accessible_group_ids, assert_group_access

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _encode_cursor(received_at: datetime, notification_id: uuid.UUID) -> str:
    raw = f"{received_at.isoformat()}|{notification_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        received_at_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(received_at_str), uuid.UUID(id_str)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="Invalid cursor.",
        ) from exc


def search_condition(q: str) -> ColumnElement[bool]:
    """Filtro `q`: sottostringa case-insensitive sull'intero contenuto.

    `COALESCE(content, content_preview)` e non `content_preview`: per i payload
    inline (la stragrande maggioranza, fino a notifyhub_inline_max_bytes) la
    ricerca copre il messaggio intero, non i primi 4096 caratteri. Per i payload
    offloaded su object storage `content` e' NULL per vincolo e il corpo vive su
    MinIO: quelle righe ricadono sulla preview, che e' quanto Postgres puo'
    vedere di loro.

    L'espressione e' identica a quella indicizzata dalla migrazione 0015
    (GIN pg_trgm): scriverla diversamente qui costerebbe un sequential scan.

    I metacaratteri di LIKE nel testo cercato vanno neutralizzati, altrimenti un
    `%` digitato dall'utente diventerebbe un jolly e un `_` un carattere
    qualsiasi: chi cerca `50%` vuole le notifiche che contengono `50%`.
    """
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    searchable = func.coalesce(Notification.content, Notification.content_preview)
    return searchable.ilike(f"%{escaped}%", escape="\\")


async def _apply_filters(
    conditions: list,
    session: AsyncSession,
    claims: AccessClaims,
    *,
    group_id: uuid.UUID | None,
    receiver_id: uuid.UUID | None,
    severity_min: Severity | None,
    source: SeveritySource | None,
    verified: bool | None,
    q: str | None,
    from_: datetime | None,
    to: datetime | None,
    write: bool = False,
) -> bool:
    """Costruisce le condizioni di filtro. Restituisce False quando il
    chiamante non puo vedere nulla (member/viewer senza gruppi associati):
    senza il vincolo di appartenenza, member e viewer leggevano le notifiche
    di tutti i gruppi del tenant, non solo dei propri.

    `write=True` per gli endpoint che modificano (bulk-read): il controllo di
    appartenenza al gruppo va fatto col metro della scrittura, non della lettura.
    """
    tenant_id = uuid.UUID(claims.tid)
    conditions.append(Notification.tenant_id == tenant_id)
    if receiver_id is not None:
        conditions.append(Notification.receiver_id == receiver_id)
    if severity_min is not None:
        conditions.append(Notification.severity >= severity_min)
    if verified is not None:
        # Revisione manuale, indipendente da read/unread: si filtra su una
        # dimensione senza toccare l'altra e le due si possono combinare.
        conditions.append(Notification.verified.is_(verified))
    if source is not None:
        # Chi ha deciso la severity, che per 'missing' e 'recovered' vuol dire
        # anche "chi ha scritto la notifica": e il filtro con cui si isolano gli
        # allarmi della sorveglianza dai messaggi inviati davvero.
        conditions.append(Notification.severity_source == source)
    if q is not None:
        conditions.append(search_condition(q))
    if from_ is not None:
        conditions.append(Notification.received_at >= from_)
    if to is not None:
        conditions.append(Notification.received_at <= to)

    receiver_conditions = [Receiver.tenant_id == tenant_id]
    if group_id is not None:
        await assert_group_access(session, claims, group_id, write=write)
        receiver_conditions.append(Receiver.group_id == group_id)

    allowed = await accessible_group_ids(session, claims)
    if allowed is not None:
        if not allowed:
            return False
        receiver_conditions.append(Receiver.group_id.in_(allowed))

    if len(receiver_conditions) > 1:
        conditions.append(
            Notification.receiver_id.in_(select(Receiver.id).where(*receiver_conditions))
        )
    return True


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    group_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    receiver_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    status_filter: NotificationStatus | None = Query(default=None, alias="status"),  # noqa: B008
    severity_min: Severity | None = Query(default=None),  # noqa: B008
    source: SeveritySource | None = Query(default=None),  # noqa: B008
    verified: bool | None = Query(default=None),  # noqa: B008
    q: str | None = Query(default=None),  # noqa: B008
    from_: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to: datetime | None = Query(default=None),  # noqa: B008
    cursor: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=20, ge=1, le=100),  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> NotificationListOut:
    """Paginazione a cursore su (received_at, id) DESC (spec 9.5): niente
    OFFSET, che degrada su tabelle grandi e puo saltare o ripetere righe se
    arrivano nuove notifiche fra una pagina e l'altra."""
    tenant_id = uuid.UUID(claims.tid)
    conditions: list = []
    visible = await _apply_filters(
        conditions,
        session,
        claims,
        group_id=group_id,
        receiver_id=receiver_id,
        severity_min=severity_min,
        source=source,
        verified=verified,
        q=q,
        from_=from_,
        to=to,
    )
    if not visible:
        return NotificationListOut(notifications=[], next_cursor=None, unread_count=0)
    if status_filter is not None:
        conditions.append(Notification.status == status_filter)

    if cursor is not None:
        cursor_received_at, cursor_id = _decode_cursor(cursor)
        conditions.append(
            func.row(Notification.received_at, Notification.id)
            < func.row(cursor_received_at, cursor_id)
        )

    result = await session.execute(
        select(Notification)
        .where(*conditions)
        .order_by(Notification.received_at.desc(), Notification.id.desc())
        .limit(limit + 1)
    )
    rows = result.scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].received_at, rows[-1].id) if has_more and rows else None

    unread_conditions = [
        Notification.tenant_id == tenant_id,
        Notification.status == NotificationStatus.UNREAD,
    ]
    allowed = await accessible_group_ids(session, claims)
    if allowed is not None:
        unread_conditions.append(
            Notification.receiver_id.in_(
                select(Receiver.id).where(
                    Receiver.tenant_id == tenant_id, Receiver.group_id.in_(allowed)
                )
            )
        )
    unread_result = await session.execute(
        select(func.count(Notification.id)).where(*unread_conditions)
    )
    unread_count = unread_result.scalar_one()

    return NotificationListOut(
        notifications=[
            NotificationListItemOut(
                id=str(n.id),
                receiver_id=str(n.receiver_id),
                content_preview=n.content_preview[:LIST_PREVIEW_CHARS],
                content_size=n.content_size,
                content_normalized=n.content_normalized,
                storage_backend=n.storage_backend.value,
                severity=n.severity,
                severity_source=n.severity_source,
                phase=n.phase,
                duration_ms=n.duration_ms,
                exit_code=n.exit_code,
                status=n.status,
                verified=n.verified,
                received_at=n.received_at,
            )
            for n in rows
        ],
        next_cursor=next_cursor,
        unread_count=unread_count,
    )


async def _get_notification_or_404(
    session: AsyncSession,
    claims: AccessClaims,
    notification_id: uuid.UUID,
    *,
    write: bool = False,
) -> Notification:
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(Notification, Receiver.group_id)
        .join(Receiver, Receiver.id == Notification.receiver_id)
        .where(Notification.id == notification_id, Notification.tenant_id == tenant_id)
    )
    row = result.first()
    if row is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Notification not found.",
        )
    notification, group_id = row
    await assert_group_access(session, claims, group_id, write=write)
    return notification


@router.get("/{notification_id}", response_model=NotificationDetailOut)
async def get_notification(
    notification_id: uuid.UUID,
    request: Request,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> NotificationDetailOut:
    notification = await _get_notification_or_404(session, claims, notification_id)
    content_url = None
    if notification.storage_backend == "object":
        # Origine risolta sulla richiesta: dietro reverse proxy il link deve
        # portare al nome pubblico, non a quello interno dell'API (core/urls.py).
        content_url = f"{public_base_url(request)}/api/v1/notifications/{notification_id}/content"

    return NotificationDetailOut(
        id=str(notification.id),
        receiver_id=str(notification.receiver_id),
        content=notification.content,
        content_url=content_url,
        content_preview=notification.content_preview,
        content_size=notification.content_size,
        content_normalized=notification.content_normalized,
        severity=notification.severity,
        severity_source=notification.severity_source,
        phase=notification.phase,
        matched_pattern=notification.matched_pattern,
        duration_ms=notification.duration_ms,
        exit_code=notification.exit_code,
        status=notification.status,
        verified=notification.verified,
        received_at=notification.received_at,
        source_ip=notification.source_ip,
    )


@router.get("/{notification_id}/content")
async def get_notification_content(
    notification_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> StreamingResponse:
    """Streaming del corpo completo, proxy da MinIO se offloaded (spec 6.5,
    9.5): mai una presigned URL esposta al browser, il download passa sempre
    dall'API, che applica ruolo e RLS."""
    notification = await _get_notification_or_404(session, claims, notification_id)

    if notification.storage_backend == "inline":
        content = notification.content or ""
        body = content.encode()
    else:
        from app.services.storage import fetch_object

        assert notification.storage_key is not None
        body = await fetch_object(notification.storage_key)

    async def _stream() -> AsyncIterator[bytes]:
        yield body

    # Content-Length sui byte che si stanno davvero mandando, non su
    # content_size: quello e la dimensione del corpo ORIGINALE, e per un payload
    # inline normalizzato (UTF-8 non valido sostituito con U+FFFD, byte NUL
    # rimossi, spec 6.2) le due misure non coincidono. Dichiarare la lunghezza
    # sbagliata fa troncare la risposta o fallire il client.
    return StreamingResponse(
        _stream(),
        media_type="text/plain",
        headers={"Content-Length": str(len(body))},
    )


@router.patch("/{notification_id}", response_model=NotificationDetailOut)
async def mark_notification_status(
    notification_id: uuid.UUID,
    body: MarkStatusIn,
    request: Request,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> NotificationDetailOut:
    """Cambia read/unread e/o verified. Serve il ruolo member: un viewer ha
    accesso in sola lettura (spec 3, ruoli) e prima poteva invece marcare come
    letta o verificata qualunque notifica dei gruppi che gli sono visibili."""
    notification = await _get_notification_or_404(session, claims, notification_id, write=True)
    if body.status is not None:
        notification.status = body.status
    if body.verified is not None:
        notification.verified = body.verified
    await session.flush()

    content_url = None
    if notification.storage_backend == "object":
        content_url = f"{public_base_url(request)}/api/v1/notifications/{notification_id}/content"

    return NotificationDetailOut(
        id=str(notification.id),
        receiver_id=str(notification.receiver_id),
        content=notification.content,
        content_url=content_url,
        content_preview=notification.content_preview,
        content_size=notification.content_size,
        content_normalized=notification.content_normalized,
        severity=notification.severity,
        severity_source=notification.severity_source,
        phase=notification.phase,
        matched_pattern=notification.matched_pattern,
        duration_ms=notification.duration_ms,
        exit_code=notification.exit_code,
        status=notification.status,
        verified=notification.verified,
        received_at=notification.received_at,
        source_ip=notification.source_ip,
    )


@router.post("/bulk-read", response_model=BulkReadOut)
async def bulk_mark_read(
    body: BulkReadIn,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> BulkReadOut:
    """Come PATCH: e una scrittura, quindi serve il ruolo member."""
    conditions: list = []
    visible = await _apply_filters(
        conditions,
        session,
        claims,
        group_id=body.group_id,
        receiver_id=body.receiver_id,
        severity_min=body.severity_min,
        source=body.source,
        verified=body.verified,
        q=body.q,
        from_=body.from_,
        to=body.to,
        write=True,
    )
    if not visible:
        return BulkReadOut(marked_read=0)
    conditions.append(Notification.status == NotificationStatus.UNREAD)

    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Notification).where(*conditions).values(status=NotificationStatus.READ)
        ),
    )
    return BulkReadOut(marked_read=result.rowcount or 0)


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: uuid.UUID,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    """Il trigger AFTER DELETE (migrazione 0002) accoda storage_key in
    pending_object_deletions per i payload offloaded (invariante I-8): qui
    basta cancellare la riga."""
    notification = await _get_notification_or_404(session, claims, notification_id, write=True)
    await session.delete(notification)
