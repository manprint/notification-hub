"""Motore dell'audit: chi ha fatto cosa, scritto nella stessa transazione del
fatto che descrive (spec 9.6).

Due sorgenti di eventi, non una:

1. Un hook `before_flush` di SQLAlchemy, che vede ogni INSERT/UPDATE/DELETE
   passato dall'ORM. Un endpoint nuovo e' tracciato per costruzione: nessuno
   deve ricordarsi di scrivere una riga di audit nel router.
2. `record_event` / `record_context_event`, per i fatti che l'ORM non vede:
   il login (riuscito o fallito), il logout, il `bulk-read` che aggiorna N
   notifiche con una sola UPDATE.

Tutto e' subordinato alla presenza di un contesto di richiesta: senza attore
umano non nasce alcun evento. E' cosi' che l'ingestion e i job Celery restano
fuori dall'audit (decisione D7 del piano) pur usando le stesse sessioni e gli
stessi modelli.

Se l'audit non si scrive, la modifica non si scrive: l'evento vive nella
transazione del chiamante, che `tenant_session` committa o annulla in blocco.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog
from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.types import AuditOutcome, UserRole
from app.models.audit_event import AuditEvent
from app.models.binding import GroupChannelBinding, ReceiverChannelOverride
from app.models.channel import DeliveryChannel
from app.models.group import Group
from app.models.invitation import Invitation
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.models.severity_preset import (
    ReceiverSeverityPreset,
    SeverityPreset,
    SeverityPresetRule,
)
from app.models.severity_rule import SeverityRule
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_group_membership import UserGroupMembership

REDACTED = "[redacted]"

# Campi che non descrivono un'intenzione dell'attore: il loro cambiamento e'
# rumore in ogni riga di audit.
ALWAYS_IGNORED = frozenset({"created_at", "updated_at"})

# Campi il cui valore non deve finire nell'audit nemmeno per il tenant a cui
# appartiene: segreti, o corpi di notifica che l'audit non deve duplicare.
MASKED_FIELDS = frozenset(
    {
        "password_hash",
        "token_hash",
        "webhook_url",
        "content",
        "content_preview",
    }
)

# Oltre questa soglia un bulk-read registra solo filtri e conteggio: l'elenco
# degli id serve a ritrovare la singola notifica, non a fotografare una coda da
# decine di migliaia di righe dentro una colonna jsonb.
BULK_IDS_CAP = 5_000

MAX_LABEL_CHARS = 255
MAX_VALUE_CHARS = 500


@dataclass(frozen=True)
class ResourceSpec:
    """Come si racconta una risorsa nell'audit."""

    resource_type: str
    label_attr: str | None = None
    # None = tutti i campi mappati; un insieme = solo quelli (il caso delle
    # notifiche, dove interessano lo stato e la verifica, non l'ingestion).
    fields: frozenset[str] | None = None
    ignored: frozenset[str] = frozenset()


RESOURCE_SPECS: dict[type, ResourceSpec] = {
    User: ResourceSpec("user", label_attr="email", ignored=frozenset({"last_login_at"})),
    Invitation: ResourceSpec("invitation", label_attr="email"),
    Group: ResourceSpec("group", label_attr="name"),
    Receiver: ResourceSpec(
        "receiver",
        label_attr="name",
        ignored=frozenset(
            {
                "last_notification_at",
                "last_start_at",
                "missing_alerted_at",
                "expected_since",
            }
        ),
    ),
    SeverityRule: ResourceSpec("severity_rule", label_attr="pattern"),
    SeverityPreset: ResourceSpec("severity_preset", label_attr="name"),
    SeverityPresetRule: ResourceSpec("severity_preset_rule", label_attr="pattern"),
    ReceiverSeverityPreset: ResourceSpec("receiver_severity_preset"),
    DeliveryChannel: ResourceSpec(
        "delivery_channel",
        label_attr="name",
        ignored=frozenset({"last_success_at", "last_error_at", "last_error"}),
    ),
    GroupChannelBinding: ResourceSpec("group_channel_binding"),
    ReceiverChannelOverride: ResourceSpec("receiver_channel_override"),
    UserGroupMembership: ResourceSpec("user_group_membership"),
    Tenant: ResourceSpec("tenant", label_attr="name"),
    Notification: ResourceSpec(
        "notification",
        label_attr="content_preview",
        fields=frozenset({"status", "verified"}),
    ),
}

# Azioni sulle notifiche: nomi propri invece di un generico
# "notification.updated", perche' e' la domanda che l'audit deve saper
# rispondere a colpo d'occhio ("chi ha verificato questa?").
ACTION_MARKED_READ = "notification.marked_read"
ACTION_MARKED_UNREAD = "notification.marked_unread"
ACTION_MARKED_VERIFIED = "notification.marked_verified"
ACTION_MARKED_UNVERIFIED = "notification.marked_unverified"
ACTION_BULK_MARKED_READ = "notification.bulk_marked_read"

NOTIFICATION_STATUS_ACTIONS = (
    ACTION_MARKED_READ,
    ACTION_MARKED_UNREAD,
    ACTION_MARKED_VERIFIED,
    ACTION_MARKED_UNVERIFIED,
    ACTION_BULK_MARKED_READ,
)

ACTION_LOGIN = "auth.login"
ACTION_LOGIN_FAILED = "auth.login_failed"
ACTION_LOGOUT = "auth.logout"


@dataclass
class AuditContext:
    """L'attore della richiesta in corso.

    `actor_email` e' risolto pigramente al primo evento: la stragrande
    maggioranza delle richieste e' in lettura e non ne produce nessuno, e una
    SELECT per richiesta pagata da tutti per servirne pochi non ha senso.
    """

    tenant_id: uuid.UUID
    actor_user_id: uuid.UUID
    actor_role: UserRole
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    actor_email: str | None = field(default=None)


_audit_context: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)


def current_audit_context() -> AuditContext | None:
    return _audit_context.get()


def set_audit_context(context: AuditContext) -> Token[AuditContext | None]:
    return _audit_context.set(context)


def reset_audit_context(token: Token[AuditContext | None]) -> None:
    _audit_context.reset(token)


def current_request_id() -> str | None:
    value = structlog.contextvars.get_contextvars().get("request_id")
    return str(value) if value is not None else None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        # Solo i segreti cifrati sono binari, e quelli passano comunque da
        # MASKED_FIELDS: qui si arriva solo per un campo binario nuovo, e
        # dirne la dimensione e' tutto cio' che l'audit puo' dire onestamente.
        return f"<{len(value)} bytes>"
    if isinstance(value, dict | list):
        return value
    text = str(value)
    return text if len(text) <= MAX_VALUE_CHARS else text[:MAX_VALUE_CHARS] + "…"


def _label_for(obj: Any, spec: ResourceSpec) -> str | None:
    if spec.label_attr is None:
        return None
    raw = getattr(obj, spec.label_attr, None)
    if raw is None:
        return None
    text = str(raw).replace("\n", " ").strip()
    return text[:MAX_LABEL_CHARS] or None


def _auditable_fields(obj: Any, spec: ResourceSpec) -> list[str]:
    mapper = inspect(type(obj)).mapper
    keys = [attr.key for attr in mapper.column_attrs]
    if spec.fields is not None:
        return [key for key in keys if key in spec.fields]
    return [key for key in keys if key not in ALWAYS_IGNORED and key not in spec.ignored]


def _masked(key: str, value: Any) -> Any:
    return REDACTED if key in MASKED_FIELDS else _jsonable(value)


def _changes_for_update(obj: Any, spec: ResourceSpec) -> dict[str, Any]:
    state = inspect(obj)
    changes: dict[str, Any] = {}
    for key in _auditable_fields(obj, spec):
        history = state.attrs[key].history
        if not history.has_changes():
            continue
        before = history.deleted[0] if history.deleted else None
        after = history.added[0] if history.added else None
        if before == after:
            continue
        changes[key] = {"before": _masked(key, before), "after": _masked(key, after)}
    return changes


def _changes_for_insert(obj: Any, spec: ResourceSpec) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in _auditable_fields(obj, spec):
        value = getattr(obj, key, None)
        if value is None:
            continue
        changes[key] = {"before": None, "after": _masked(key, value)}
    return changes


def record_event(
    session: Session | AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    actor_email: str,
    actor_role: UserRole,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    resource_label: str | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    changes: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    """Aggiunge l'evento alla sessione del chiamante, senza flush ne commit:
    l'evento vive o muore con la transazione che descrive."""
    audit_event = AuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_email=actor_email[:320],
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_label=resource_label[:MAX_LABEL_CHARS] if resource_label else None,
        outcome=outcome,
        ip=ip,
        user_agent=user_agent[:255] if user_agent else None,
        request_id=request_id,
        changes=changes or None,
        context=context or None,
    )
    session.add(audit_event)
    return audit_event


async def resolve_actor_email(session: AsyncSession, context: AuditContext) -> str:
    if context.actor_email is None:
        result = await session.execute(select(User.email).where(User.id == context.actor_user_id))
        context.actor_email = result.scalar_one_or_none() or str(context.actor_user_id)
    return context.actor_email


async def record_context_event(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    resource_label: str | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    changes: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> AuditEvent | None:
    """Evento esplicito per cio' che l'ORM non vede. Senza contesto di
    richiesta non scrive nulla: e' il caso dei job Celery e dell'ingestion."""
    ctx = current_audit_context()
    if ctx is None:
        return None
    actor_email = await resolve_actor_email(session, ctx)
    return record_event(
        session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.actor_user_id,
        actor_email=actor_email,
        actor_role=ctx.actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_label=resource_label,
        outcome=outcome,
        changes=changes,
        context=context,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
    )


def _actor_email_sync(session: Session, ctx: AuditContext) -> str:
    """Risoluzione dell'email dentro l'hook, che e' sincrono.

    Passa dalla connessione invece che dalla sessione: una query ORM durante
    `before_flush` rischierebbe un autoflush rientrante proprio mentre si sta
    decidendo cosa flushare.
    """
    if ctx.actor_email is None:
        row = session.connection().execute(select(User.email).where(User.id == ctx.actor_user_id))
        ctx.actor_email = row.scalar_one_or_none() or str(ctx.actor_user_id)
    return ctx.actor_email


def _notification_actions(changes: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    status = changes.get("status")
    if status is not None:
        actions.append(ACTION_MARKED_READ if status["after"] == "read" else ACTION_MARKED_UNREAD)
    verified = changes.get("verified")
    if verified is not None:
        actions.append(ACTION_MARKED_VERIFIED if verified["after"] else ACTION_MARKED_UNVERIFIED)
    return actions


def _pending_events(session: Session, ctx: AuditContext) -> list[dict[str, Any]]:
    """Traduce lo stato della sessione in eventi, senza ancora toccarla."""
    pending: list[dict[str, Any]] = []

    def collect(obj: Any, kind: str) -> None:
        spec = RESOURCE_SPECS.get(type(obj))
        if spec is None:
            return
        if kind == "updated":
            changes = _changes_for_update(obj, spec)
        elif kind == "created":
            changes = _changes_for_insert(obj, spec)
        else:
            changes = {}
        if kind == "updated" and not changes:
            return

        tenant_id = getattr(obj, "tenant_id", None) or ctx.tenant_id
        resource_id = getattr(obj, "id", None)
        common = {
            "tenant_id": tenant_id,
            "resource_type": spec.resource_type,
            "resource_id": resource_id,
            "resource_label": _label_for(obj, spec),
            "changes": changes,
        }

        if spec.resource_type == "notification" and kind == "updated":
            # Una PATCH puo' cambiare lettura e verifica insieme: sono due
            # fatti distinti e vanno cercabili separatamente.
            for action in _notification_actions(changes):
                field_key = "status" if "read" in action else "verified"
                pending.append(
                    {**common, "action": action, "changes": {field_key: changes[field_key]}}
                )
            return
        if spec.resource_type == "notification":
            # Le notifiche nascono dall'ingestion, che non ha attore: un
            # create/delete con contesto di richiesta e' la purge o un replay,
            # gia' raccontati altrove.
            return

        pending.append({**common, "action": f"{spec.resource_type}.{kind}"})

    for obj in session.new:
        collect(obj, "created")
    for obj in session.dirty:
        if session.is_modified(obj, include_collections=False):
            collect(obj, "updated")
    for obj in session.deleted:
        collect(obj, "deleted")

    return pending


@event.listens_for(Session, "before_flush")
def _audit_before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    ctx = current_audit_context()
    if ctx is None:
        return
    pending = _pending_events(session, ctx)
    if not pending:
        return

    actor_email = _actor_email_sync(session, ctx)
    for item in pending:
        record_event(
            session,
            actor_user_id=ctx.actor_user_id,
            actor_email=actor_email,
            actor_role=ctx.actor_role,
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            request_id=ctx.request_id,
            **item,
        )
