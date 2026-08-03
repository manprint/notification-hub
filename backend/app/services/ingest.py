"""Pipeline di ingestion del modulo http_raw (spec 6.1, 6.2, 6.5, 7)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import ingest_session
from app.db.types import NotificationStatus, Severity, SeveritySource
from app.models.receiver import Receiver
from app.models.severity_rule import SeverityRule
from app.services.severity import resolve_severity_async
from app.services.storage import object_key, should_use_object_storage

CONTENT_PREVIEW_CHARS = 4096


@dataclass
class ReceiverLookup:
    id: uuid.UUID
    tenant_id: uuid.UUID
    group_id: uuid.UUID
    status: str
    max_body_bytes: int
    rate_limit_per_min: int
    default_severity: Severity
    exit_code_severity: Severity | None


async def resolve_receiver_by_slug(slug: str) -> ReceiverLookup | None:
    """Risoluzione slug -> receiver sul pool notifyhub_ingest, senza contesto di
    tenant (spec 5.2, 5.3). Restituisce None per slug inesistente O disabilitato:
    il chiamante decide come rispondere, ma qui non si distingue nulla, a monte
    dell'invariante I-2."""
    async with ingest_session() as session:
        result = await session.execute(select(Receiver).where(Receiver.slug == slug))
        receiver = result.scalar_one_or_none()
        if receiver is None:
            return None
        return ReceiverLookup(
            id=receiver.id,
            tenant_id=receiver.tenant_id,
            group_id=receiver.group_id,
            status=receiver.status,
            max_body_bytes=receiver.max_body_bytes,
            rate_limit_per_min=receiver.rate_limit_per_min,
            default_severity=receiver.default_severity,
            exit_code_severity=receiver.exit_code_severity,
        )


def normalize_body(raw: bytes) -> tuple[str, bool]:
    """Decodifica UTF-8 permissiva + rimozione dei byte NUL (spec 6.2).

    L'ingestion non deve mai fallire per il contenuto (invariante I-7): qualunque
    sequenza di byte produce una stringa persistibile. `content_normalized` e
    true se la decodifica ha dovuto sostituire byte non validi o se erano
    presenti byte NUL, che Postgres rifiuta comunque in una colonna text.
    """
    try:
        raw.decode("utf-8")
        invalid_utf8 = False
    except UnicodeDecodeError:
        invalid_utf8 = True

    text = raw.decode("utf-8", errors="replace")
    had_nul = "\x00" in text
    text = text.replace("\x00", "")

    return text, (invalid_utf8 or had_nul)


async def fetch_severity_rules(session: AsyncSession, receiver_id: uuid.UUID) -> list[SeverityRule]:
    result = await session.execute(
        select(SeverityRule)
        .where(SeverityRule.receiver_id == receiver_id, SeverityRule.enabled.is_(True))
        .order_by(SeverityRule.priority.asc())
    )
    return list(result.scalars().all())


@dataclass
class PreparedNotification:
    """Tutto cio che serve per decidere lo storage backend PRIMA di scrivere
    su Postgres: l'id e generato qui perche entra nella chiave dell'oggetto
    MinIO (spec 6.5) e deve esistere prima di un eventuale PUT."""

    id: uuid.UUID
    normalized_text: str
    content_normalized: bool
    original_size: int
    use_object_storage: bool
    storage_key: str | None
    severity: Severity
    severity_source: SeveritySource
    matched_pattern: str | None


async def prepare_notification(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    receiver_id: uuid.UUID,
    raw_body: bytes,
    header_severity: str | None,
    query_severity: str | None,
    default_severity: Severity,
    exit_code: int | None = None,
    exit_code_severity: Severity | None = None,
) -> PreparedNotification:
    """Normalizza, risolve la severity e decide lo storage backend. Non scrive
    nulla: il chiamante fa l'eventuale PUT su MinIO, poi chiama
    persist_notification per l'insert.

    Le regole vedono il contenuto INTERO: nessun campione, nessuna troncatura.
    Sopra una certa dimensione la scansione va su un thread (severity.py), cosi
    un corpo grande non blocca l'event loop per tutte le altre richieste."""
    normalized_text, content_normalized = normalize_body(raw_body)
    original_size = len(raw_body)

    rules = await fetch_severity_rules(session, receiver_id)
    resolution = await resolve_severity_async(
        header_severity=header_severity,
        query_severity=query_severity,
        rules=rules,
        content=normalized_text,
        default_severity=default_severity,
        exit_code=exit_code,
        exit_code_severity=exit_code_severity,
    )

    notification_id = uuid.uuid4()
    use_object_storage = should_use_object_storage(original_size)
    storage_key = object_key(tenant_id, notification_id) if use_object_storage else None

    return PreparedNotification(
        id=notification_id,
        normalized_text=normalized_text,
        content_normalized=content_normalized,
        original_size=original_size,
        use_object_storage=use_object_storage,
        storage_key=storage_key,
        severity=resolution.severity,
        severity_source=resolution.source,
        matched_pattern=resolution.matched_pattern,
    )


async def persist_notification(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    receiver_id: uuid.UUID,
    prepared: PreparedNotification,
    source_ip: str | None,
    metadata: dict | None = None,
) -> None:
    """Insert della Notification. Va chiamato DOPO l'eventuale PUT su MinIO
    riuscito (spec 6.5): un PUT fallito non deve mai lasciare una riga scritta."""
    from app.models.notification import Notification

    content_preview = prepared.normalized_text[:CONTENT_PREVIEW_CHARS]

    notification = Notification(
        id=prepared.id,
        tenant_id=tenant_id,
        receiver_id=receiver_id,
        storage_backend="object" if prepared.use_object_storage else "inline",
        content=None if prepared.use_object_storage else prepared.normalized_text,
        storage_key=prepared.storage_key,
        content_preview=content_preview,
        content_size=prepared.original_size,
        content_normalized=prepared.content_normalized,
        severity=prepared.severity,
        severity_source=prepared.severity_source,
        matched_pattern=prepared.matched_pattern,
        status=NotificationStatus.UNREAD,
        received_at=datetime.now(UTC),
        source_ip=source_ip,
        meta=metadata or {},
    )
    session.add(notification)
    await session.flush()
