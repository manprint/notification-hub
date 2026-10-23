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
from sqlalchemy import Select, func, literal_column, select, union
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from starlette.responses import StreamingResponse

from app.api.deps import db, require_admin
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.db.session import tenant_session
from app.db.types import AuditOutcome
from app.models.audit_event import AuditEvent
from app.schemas.audit import AuditEventListOut, AuditEventOut
from app.schemas.notification import UtcDatetime, as_utc
from app.services.audit import NOTIFICATION_STATUS_ACTIONS
from app.services.audit_location import EMPTY, Location, resolve_locations

router = APIRouter(prefix="/audit", tags=["audit"])

# Tetto all'export: un CSV e' un file che qualcuno scarica ora, non un dump
# storico. Oltre questa soglia si restringono i filtri.
EXPORT_MAX_ROWS = 50_000
# Righe per blocco nell'export in streaming: con id a pieno carico una riga pesa
# ~200 KB, cento righe restano sotto i 20 MB in memoria.
EXPORT_BATCH_ROWS = 100

EXPORT_COLUMNS = [
    "occurred_at",
    "actor_email",
    "actor_role",
    "action",
    "resource_type",
    "resource_id",
    "resource_label",
    "group_name",
    "receiver_name",
    "outcome",
    "ip",
    "request_id",
    "changes",
    "context",
]


# Celle che Excel e LibreOffice valutano come formule (OWASP, CSV injection). Il
# corpo di una notifica e i nomi di gruppi e receiver sono testo libero, quindi
# una cella che inizia cosi' va neutralizzata con un apice davanti.
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(CSV_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _csv_row(record: dict[str, Any]) -> list[Any]:
    return [
        _csv_cell(
            json.dumps(record[column], ensure_ascii=False)
            if isinstance(record[column], dict)
            else record[column]
        )
        for column in EXPORT_COLUMNS
    ]


def _encode_cursor(occurred_at: datetime, event_id: uuid.UUID) -> str:
    raw = f"{occurred_at.isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        occurred_at_str, id_str = raw.split("|", 1)
        return as_utc(datetime.fromisoformat(occurred_at_str)), uuid.UUID(id_str)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="Invalid cursor.",
        ) from exc


# Il contesto di un bulk-read si legge con `->` e la chiave come letterale: solo
# l'espressione identica a quella indicizzata dal GIN (migrazione 0016) puo'
# usarlo. La forma a sottoscrizione `context['notification_ids']` non ci
# corrisponde e fa scorrere la tabella.
_NOTIFICATION_IDS = AuditEvent.context.op("->", return_type=JSONB)(
    literal_column("'notification_ids'")
)


def notification_in_context(notification_id: uuid.UUID) -> ColumnElement[bool]:
    """Il bulk-read che ha toccato questa notifica, per l'indice GIN."""
    return _NOTIFICATION_IDS.contains(func.jsonb_build_array(str(notification_id)))


def _notification_event_ids(claims: AccessClaims, notification_id: uuid.UUID) -> Select[Any]:
    """Id degli eventi che riguardano una notifica: la PATCH singola la porta in
    `resource_id`, il bulk-read in `context`, che e' l'unico posto dove puo'
    stare visto che un evento solo ne copre N.

    Due rami e un CTE materializzato, non un OR fra le colonne: con l'OR
    Postgres sceglie l'indice per tenant in ordine di data e scarta riga per
    riga, anche duecentomila eventi per una notifica toccata una volta sola.
    """
    tenant_id = uuid.UUID(claims.tid)
    by_resource = select(AuditEvent.id).where(
        AuditEvent.tenant_id == tenant_id,
        AuditEvent.resource_type == "notification",
        AuditEvent.resource_id == notification_id,
    )
    by_context = select(AuditEvent.id).where(
        AuditEvent.tenant_id == tenant_id,
        notification_in_context(notification_id),
    )
    matched = union(by_resource, by_context).cte("notification_events").prefix_with("MATERIALIZED")
    return select(matched.c.id)


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
) -> Select[AuditEvent]:
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
        conditions.append(AuditEvent.id.in_(_notification_event_ids(claims, notification_id)))
    return select(AuditEvent).where(*conditions)


def _to_out(event: AuditEvent, location: Location = EMPTY) -> AuditEventOut:
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
        group_id=location.group_id,
        group_name=location.group_name,
        receiver_id=location.receiver_id,
        receiver_name=location.receiver_name,
        outcome=event.outcome,
        ip=event.ip,
        user_agent=event.user_agent,
        request_id=event.request_id,
        changes=event.changes,
        context=event.context,
    )


async def _paginated(
    session: AsyncSession,
    query: Select[AuditEvent],
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
    posizioni = await resolve_locations(session, rows)
    return AuditEventListOut(
        events=[_to_out(row, posizioni.get(row.id, EMPTY)) for row in rows],
        next_cursor=next_cursor,
    )


@router.get("/events", response_model=AuditEventListOut)
async def list_audit_events(
    actor_user_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    action: str | None = Query(default=None),  # noqa: B008
    resource_type: str | None = Query(default=None),  # noqa: B008
    resource_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    outcome: AuditOutcome | None = Query(default=None),  # noqa: B008
    from_: UtcDatetime | None = Query(default=None, alias="from"),  # noqa: B008
    to: UtcDatetime | None = Query(default=None),  # noqa: B008
    cursor: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db, scope="function"),  # noqa: B008
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
    from_: UtcDatetime | None = Query(default=None, alias="from"),  # noqa: B008
    to: UtcDatetime | None = Query(default=None),  # noqa: B008
    cursor: str | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db, scope="function"),  # noqa: B008
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
    from_: UtcDatetime | None = Query(default=None, alias="from"),  # noqa: B008
    to: UtcDatetime | None = Query(default=None),  # noqa: B008
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db, scope="function"),  # noqa: B008
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
    # Il conteggio, non le righe, decide il 422: prima di inviare un byte.
    count = await session.execute(
        select(func.count()).select_from(query.limit(EXPORT_MAX_ROWS + 1).subquery())
    )
    if count.scalar_one() > EXPORT_MAX_ROWS:
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

    tenant_id = uuid.UUID(claims.tid)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
    if format == "json":
        media_type = "application/json"
        filename = f"audit-{stamp}.json"
    else:
        media_type = "text/csv"
        filename = f"audit-{stamp}.csv"

    async def _righe() -> AsyncIterator[bytes]:
        # Le righe escono a blocchi in ordine (occurred_at, id) DESC, con un
        # cursore sull'ultima di ciascun blocco: l'export intero non sta mai in
        # memoria. Il blocco e' piccolo perche' una riga puo' portare fino a
        # BULK_IDS_CAP id. Lo stesso contesto che si legge a schermo: gruppo e
        # receiver si risolvono per blocco, non per tutte le righe.
        #
        # Ogni blocco apre e chiude la sua sessione prima di consegnare i byte: un
        # download lento non tiene una connessione del pool per tutta la sua durata
        # (con qualche export lento il pool si esauriva e il resto aspettava). Il
        # cursore keyset rende i blocchi indipendenti. Di conseguenza l'export non
        # legge uno snapshot unico: gli eventi nuovi entrano in testa all'ordine DESC
        # e non spostano la pagina successiva.
        if format == "json":
            yield b"["
        else:
            intestazione = io.StringIO()
            csv.writer(intestazione).writerow(EXPORT_COLUMNS)
            yield intestazione.getvalue().encode()

        primo = True
        emesse = 0
        cursore: tuple[datetime, uuid.UUID] | None = None
        while emesse < EXPORT_MAX_ROWS:
            blocco = query
            if cursore is not None:
                blocco = blocco.where(
                    func.row(AuditEvent.occurred_at, AuditEvent.id) < func.row(*cursore)
                )
            async with tenant_session(tenant_id) as sessione:
                result = await sessione.execute(
                    blocco.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(
                        EXPORT_BATCH_ROWS
                    )
                )
                righe = result.scalars().all()
                if not righe:
                    break
                posizioni = await resolve_locations(sessione, righe)
                records = [
                    _to_out(row, posizioni.get(row.id, EMPTY)).model_dump(mode="json")
                    for row in righe
                ]
            if format == "json":
                parti = [json.dumps(record, ensure_ascii=False) for record in records]
                yield (("" if primo else ", ") + ", ".join(parti)).encode()
            else:
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                for record in records:
                    writer.writerow(_csv_row(record))
                yield buffer.getvalue().encode()
            primo = False
            emesse += len(righe)
            if len(righe) < EXPORT_BATCH_ROWS:
                break
            cursore = (righe[-1].occurred_at, righe[-1].id)

        if format == "json":
            yield b"]"

    # Il corpo non usa la sessione della richiesta: `db` ha scope "function" e chiude
    # prima che il corpo parta. Ogni blocco di _righe apre la sua sessione sullo
    # stesso tenant, e cosi' RLS resta attiva per tutta la lettura.
    return StreamingResponse(
        _righe(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
