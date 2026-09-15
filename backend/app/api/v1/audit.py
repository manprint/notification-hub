"""Consultazione dell'audit (spec 9.6).

Tutto qui dentro e' `require_admin`: owner e admin. Un member o un viewer
prende 403 anche sui propri eventi, perche' "chi ha fatto cosa" e' una domanda
di governo del tenant, non di lavoro quotidiano; cio' che serve a lavorare
(chi ha letto o verificato una notifica) sta sulla notifica stessa.
"""

import base64
import binascii
import csv
import io
import json
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.api.deps import db, require_admin
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.db.types import AuditOutcome
from app.models.audit_event import AuditEvent
from app.schemas.audit import AuditEventListOut, AuditEventOut
from app.services.audit import NOTIFICATION_STATUS_ACTIONS

router = APIRouter(prefix="/audit", tags=["audit"])

# Tetto all'export: un CSV e' un file che qualcuno scarica ora, non un dump
# storico. Oltre questa soglia si restringono i filtri.
EXPORT_MAX_ROWS = 50_000

EXPORT_COLUMNS = [
    "occurred_at",
    "actor_email",
    "actor_role",
    "action",
    "resource_type",
    "resource_id",
    "resource_label",
    "outcome",
    "ip",
    "request_id",
    "changes",
    "context",
]


def _encode_cursor(occurred_at: datetime, event_id: uuid.UUID) -> str:
    raw = f"{occurred_at.isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        occurred_at_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(occurred_at_str), uuid.UUID(id_str)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="Invalid cursor.",
        ) from exc


def _base_query(
    claims: AccessClaims,
    *,
    actor_user_id: uuid.UUID | None,
    action: str | None,
    resource_type: str | None,
    resource_id: uuid.UUID | None,
    outcome: AuditOutcome | None,
    from_: datetime | None,
    to: datetime | None,
    notification_id: uuid.UUID | None = None,
    only_notification_status: bool = False,
) -> Select[tuple[AuditEvent]]:
    conditions: list[Any] = [AuditEvent.tenant_id == uuid.UUID(claims.tid)]
    if actor_user_id is not None:
        conditions.append(AuditEvent.actor_user_id == actor_user_id)
    if action is not None:
        conditions.append(AuditEvent.action == action)
    if resource_type is not None:
        conditions.append(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        conditions.append(AuditEvent.resource_id == resource_id)
    if outcome is not None:
        conditions.append(AuditEvent.outcome == outcome)
    if from_ is not None:
        conditions.append(AuditEvent.occurred_at >= from_)
    if to is not None:
        conditions.append(AuditEvent.occurred_at <= to)
    if only_notification_status:
        conditions.append(AuditEvent.action.in_(NOTIFICATION_STATUS_ACTIONS))
    if notification_id is not None:
        # Due forme per lo stesso fatto: la PATCH singola porta l'id in
        # `resource_id`, il bulk-read lo porta dentro `context`, che e' l'unico
        # posto dove puo' stare visto che un evento solo ne copre N. L'indice
        # GIN su (context -> 'notification_ids') rende il secondo ramo
        # indicizzato quanto il primo (migrazione 0016).
        conditions.append(
            or_(
                AuditEvent.resource_id == notification_id,
                cast(AuditEvent.context["notification_ids"], JSONB).op("@>")(
                    func.jsonb_build_array(str(notification_id))
                ),
            )
        )
    return select(AuditEvent).where(*conditions)


def _to_out(event: AuditEvent) -> AuditEventOut:
    return AuditEventOut(
        id=str(event.id),
        occurred_at=event.occurred_at,
        actor_user_id=str(event.actor_user_id) if event.actor_user_id else None,
        actor_email=event.actor_email,
        actor_role=event.actor_role,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=str(event.resource_id) if event.resource_id else None,
        resource_label=event.resource_label,
        outcome=event.outcome,
        ip=event.ip,
        user_agent=event.user_agent,
        request_id=event.request_id,
        changes=event.changes,
        context=event.context,
    )


async def _paginated(
    session: AsyncSession,
    query: Select[tuple[AuditEvent]],
    cursor: str | None,
    limit: int,
) -> AuditEventListOut:
    if cursor is not None:
        cursor_occurred_at, cursor_id = _decode_cursor(cursor)
        query = query.where(
            func.row(AuditEvent.occurred_at, AuditEvent.id)
            < func.row(cursor_occurred_at, cursor_id)
        )

    result = await session.execute(
        query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
    )
    rows: Sequence[AuditEvent] = result.scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].occurred_at, rows[-1].id) if has_more and rows else None
    return AuditEventListOut(events=[_to_out(row) for row in rows], next_cursor=next_cursor)


@router.get("/events", response_model=AuditEventListOut)
async def list_audit_events(
    actor_user_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    action: str | None = Query(default=None),  # noqa: B008
    resource_type: str | None = Query(default=None),  # noqa: B008
    resource_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    outcome: AuditOutcome | None = Query(default=None),  # noqa: B008
    from_: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to: datetime | None = Query(default=None),  # noqa: B008
    cursor: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> AuditEventListOut:
    """Paginazione a cursore su (occurred_at, id) DESC, come le notifiche."""
    query = _base_query(
        claims,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        from_=from_,
        to=to,
    )
    return await _paginated(session, query, cursor, limit)


@router.get("/notification-status", response_model=AuditEventListOut)
async def list_notification_status_events(
    notification_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    actor_user_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    action: str | None = Query(default=None),  # noqa: B008
    from_: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to: datetime | None = Query(default=None),  # noqa: B008
    cursor: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> AuditEventListOut:
    """Vista filtrata sulle sole letture e verifiche: stessa tabella, stessa
    ritenzione, stessa verita' (decisione D5 del piano)."""
    query = _base_query(
        claims,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=None,
        resource_id=None,
        outcome=None,
        from_=from_,
        to=to,
        notification_id=notification_id,
        only_notification_status=True,
    )
    return await _paginated(session, query, cursor, limit)


@router.get("/export")
async def export_audit_events(
    format: str = Query(default="csv", pattern="^(csv|json)$"),  # noqa: A002, B008
    notification_status_only: bool = Query(default=False),  # noqa: B008
    notification_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    actor_user_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    action: str | None = Query(default=None),  # noqa: B008
    resource_type: str | None = Query(default=None),  # noqa: B008
    resource_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    outcome: AuditOutcome | None = Query(default=None),  # noqa: B008
    from_: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to: datetime | None = Query(default=None),  # noqa: B008
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> StreamingResponse:
    """Esporta cio' che i filtri selezionano, fino a EXPORT_MAX_ROWS righe."""
    query = _base_query(
        claims,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        from_=from_,
        to=to,
        notification_id=notification_id,
        only_notification_status=notification_status_only,
    )
    result = await session.execute(
        query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(
            EXPORT_MAX_ROWS + 1
        )
    )
    rows = result.scalars().all()
    if len(rows) > EXPORT_MAX_ROWS:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=(
                f"The filters select more than {EXPORT_MAX_ROWS} events. "
                "Narrow the date range and retry."
            ),
            extra={"max_rows": EXPORT_MAX_ROWS},
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
    if format == "json":
        payload = json.dumps(
            [_to_out(row).model_dump(mode="json") for row in rows], ensure_ascii=False
        ).encode()
        media_type = "application/json"
        filename = f"audit-{stamp}.json"
    else:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(EXPORT_COLUMNS)
        for row in rows:
            record = _to_out(row).model_dump(mode="json")
            writer.writerow(
                [
                    json.dumps(record[column], ensure_ascii=False)
                    if isinstance(record[column], dict)
                    else record[column]
                    for column in EXPORT_COLUMNS
                ]
            )
        payload = buffer.getvalue().encode()
        media_type = "text/csv"
        filename = f"audit-{stamp}.csv"

    async def _stream() -> AsyncIterator[bytes]:
        yield payload

    return StreamingResponse(
        _stream(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
        },
    )
