"""Job Celery Beat di manutenzione (spec 11). Girano con il ruolo
notifyhub_app, senza privilegi di bypass: quelli che toccano dati di tenant
iterano i tenant e impostano app.tenant_id per ciascuno (spec 5.3)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.metrics import maintenance_job_runs_total
from app.db.sync_session import sync_session_factory, tenant_session_sync
from app.db.types import (
    DeliveryStatus,
    NotificationStatus,
    ReceiverStatus,
    Severity,
    SeveritySource,
    TenantStatus,
)
from app.models.audit_event import AuditEvent
from app.models.delivery import Delivery
from app.models.group import Group
from app.models.invitation import Invitation
from app.models.notification import Notification
from app.models.object_deletion import PendingObjectDeletion
from app.models.receiver import Receiver
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.services.outbound_resolver import create_deliveries_for_notification_sync
from app.services.surveillance import (
    InvalidScheduleError,
    alert_deadline,
    missing_content,
    recovered_content,
    reference_instant,
    schedule_from_receiver,
)
from app.tasks.celery_app import celery_app
from app.tasks.enqueue import enqueue_delivery

logger = get_logger(__name__)

PURGE_BATCH_SIZE = 10_000


def _all_tenant_ids() -> list[uuid.UUID]:
    with sync_session_factory() as session:
        return [row[0] for row in session.execute(select(Tenant.id)).all()]


@celery_app.task(name="app.tasks.maintenance.purge_notifications")
def purge_notifications() -> None:
    """Per ogni tenant con retention_days non NULL, elimina le notifiche piu
    vecchie a batch di 10.000 righe (spec 11)."""
    with sync_session_factory() as session:
        tenants = session.execute(
            select(Tenant.id, Tenant.retention_days).where(Tenant.retention_days.isnot(None))
        ).all()

    for tenant_id, retention_days in tenants:
        if retention_days is None:  # gia' escluso dalla query
            continue
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        deleted_total = 0
        while True:
            with tenant_session_sync(tenant_id) as session:
                ids = (
                    session.execute(
                        select(Notification.id)
                        .where(
                            Notification.tenant_id == tenant_id, Notification.received_at < cutoff
                        )
                        .order_by(Notification.received_at.asc(), Notification.id.asc())
                        .limit(PURGE_BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                    )
                    .scalars()
                    .all()
                )
                if ids:
                    session.execute(delete(Notification).where(Notification.id.in_(ids)))
                batch_size = len(ids)
            deleted_total += batch_size
            if batch_size < PURGE_BATCH_SIZE:
                break
        logger.info("purge_notifications_done", tenant_id=str(tenant_id), deleted=deleted_total)
    maintenance_job_runs_total.labels(job="purge_notifications", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.purge_audit_events")
def purge_audit_events() -> None:
    """Ritenzione dell'audit, separata da quella delle notifiche (spec 9.6).

    `audit_retention_days` e' di default 365 contro i 90 di `retention_days`:
    l'audit deve poter raccontare chi ha gestito una notifica anche quando
    quella notifica e' gia stata cancellata. NULL = conservazione illimitata,
    e questi tenant non vengono nemmeno letti dalla query qui sotto.
    """
    with sync_session_factory() as session:
        tenants = session.execute(
            select(Tenant.id, Tenant.audit_retention_days).where(
                Tenant.audit_retention_days.isnot(None)
            )
        ).all()

    for tenant_id, retention_days in tenants:
        if retention_days is None:  # gia' escluso dalla query
            continue
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        deleted_total = 0
        while True:
            with tenant_session_sync(tenant_id) as session:
                # Niente SELECT ... FOR UPDATE SKIP LOCKED come nelle altre
                # purge: bloccare una riga richiede il privilegio di UPDATE,
                # che su audit_events e' revocato apposta (migrazione 0016).
                # Il lock di riga della DELETE basta: questo job e' l'unico
                # scrittore che cancella, e gira una volta al giorno.
                oldest = (
                    select(AuditEvent.id)
                    .where(
                        AuditEvent.tenant_id == tenant_id,
                        AuditEvent.occurred_at < cutoff,
                    )
                    .order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
                    .limit(PURGE_BATCH_SIZE)
                    .scalar_subquery()
                )
                result = cast(
                    CursorResult[Any],
                    session.execute(delete(AuditEvent).where(AuditEvent.id.in_(oldest))),
                )
                batch_size = result.rowcount or 0
            deleted_total += batch_size
            if batch_size < PURGE_BATCH_SIZE:
                break
        logger.info("purge_audit_events_done", tenant_id=str(tenant_id), deleted=deleted_total)
    maintenance_job_runs_total.labels(job="purge_audit_events", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.purge_deliveries")
def purge_deliveries() -> None:
    """Elimina le delivery `sent` piu vecchie di 30 giorni; le `dead` restano
    finche non archiviate manualmente (spec 11)."""
    cutoff = datetime.now(UTC) - timedelta(days=30)
    for tenant_id in _all_tenant_ids():
        with tenant_session_sync(tenant_id) as session:
            session.execute(
                delete(Delivery).where(
                    Delivery.tenant_id == tenant_id,
                    Delivery.status == DeliveryStatus.SENT,
                    Delivery.sent_at < cutoff,
                )
            )
    maintenance_job_runs_total.labels(job="purge_deliveries", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.cleanup_tokens")
def cleanup_tokens() -> None:
    """Elimina refresh token scaduti e inviti scaduti (spec 11).
    Tabelle scoped-per-tenant: itera i tenant come tutto il resto.

    Un token revocato dalla rotazione resta fino alla sua scadenza: il riuso di
    un token gia' ruotato va rilevato per tutta la sua validita' (spec 4.1), e
    cancellarlo alla rotazione farebbe passare il riuso per un token ignoto.
    """
    now = datetime.now(UTC)
    for tenant_id in _all_tenant_ids():
        with tenant_session_sync(tenant_id) as session:
            session.execute(
                delete(RefreshToken).where(
                    RefreshToken.tenant_id == tenant_id,
                    RefreshToken.expires_at < now,
                )
            )
            session.execute(
                delete(Invitation).where(
                    Invitation.tenant_id == tenant_id, Invitation.expires_at < now
                )
            )
    maintenance_job_runs_total.labels(job="cleanup_tokens", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.reconcile_deliveries")
def reconcile_deliveries() -> None:
    """Ripesca le delivery pending/failed con next_attempt_at scaduto (il
    broker che perde un messaggio) e le sending con locked_at piu vecchio di
    10 minuti (il worker ucciso a meta lavoro). Spec 8.2, 11: e la garanzia di
    consegna, l'hook after_commit e solo l'ottimizzazione di latenza."""
    now = datetime.now(UTC)
    stuck_cutoff = now - timedelta(minutes=10)
    requeued = 0

    for tenant_id in _all_tenant_ids():
        with tenant_session_sync(tenant_id) as session:
            # Si riaccodano anche quelle il cui canale e' stato disabilitato:
            # dispatch_delivery le rende terminali (`dead`). Filtrarle qui
            # lascerebbe `pending` per sempre una riga il cui messaggio broker
            # sia andato perso prima della disabilitazione.
            due = (
                session.execute(
                    select(Delivery.id).where(
                        Delivery.tenant_id == tenant_id,
                        Delivery.status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
                        Delivery.next_attempt_at <= now,
                    )
                )
                .scalars()
                .all()
            )

            stuck = (
                session.execute(
                    select(Delivery.id).where(
                        Delivery.tenant_id == tenant_id,
                        Delivery.status == DeliveryStatus.SENDING,
                        Delivery.locked_at < stuck_cutoff,
                    )
                )
                .scalars()
                .all()
            )

            # Riclaim condizionale: l'UPDATE rivaluta `sending` e locked_at sulla
            # riga corrente. Se il proprietario ha committato `sent` dopo la SELECT,
            # la riga non viene toccata e non viene riaccodata: riscriverla a
            # `failed` la farebbe consegnare due volte.
            reclaimed: Sequence[uuid.UUID] = []
            if stuck:
                reclaimed = (
                    session.execute(
                        update(Delivery)
                        .where(
                            Delivery.tenant_id == tenant_id,
                            Delivery.id.in_(stuck),
                            Delivery.status == DeliveryStatus.SENDING,
                            Delivery.locked_at < stuck_cutoff,
                        )
                        .values(status=DeliveryStatus.FAILED, locked_at=None)
                        .returning(Delivery.id)
                        .execution_options(synchronize_session=False)
                    )
                    .scalars()
                    .all()
                )

        # Un broker che rifiuta un messaggio non deve fermare il giro: la riga resta
        # pending (o failed, se riclamata) e la riprende il giro successivo.
        for delivery_id in list(due) + list(reclaimed):
            try:
                enqueue_delivery(str(delivery_id), str(tenant_id))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "reconcile_enqueue_failed",
                    tenant_id=str(tenant_id),
                    delivery_id=str(delivery_id),
                    exc_info=True,
                )
                continue
            requeued += 1

    logger.info("reconcile_deliveries_done", requeued=requeued)
    maintenance_job_runs_total.labels(job="reconcile_deliveries", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.drain_object_deletions")
def drain_object_deletions() -> None:
    """Svuota pending_object_deletions cancellando gli oggetti da MinIO (spec
    6.5, 11). Tabella fuori da RLS, nessun contesto di tenant necessario. Dopo
    10 tentativi falliti la riga resta e alimenta una metrica di allarme."""
    import boto3
    from botocore.config import Config

    from app.core.config import get_settings, s3_timeouts

    settings = get_settings()
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.notifyhub_s3_endpoint,
        aws_access_key_id=settings.notifyhub_s3_access_key,
        aws_secret_access_key=settings.notifyhub_s3_secret_key,
        region_name=settings.notifyhub_s3_region,
        # Timeout e tentativi espliciti, dalle impostazioni NOTIFYHUB_S3_*: con MinIO
        # irraggiungibile i default di botocore (60s per tentativo) tenevano la
        # transazione aperta per ore.
        config=Config(**s3_timeouts()),
    )

    with sync_session_factory() as session:
        drained = 0
        # Una riga alla volta, con cursore keyset: ogni riga e' bloccata (SKIP
        # LOCKED) e committata da sola, cosi' il lock non sopravvive al commit e un
        # run concorrente non la riprende. Una riga che fallisce non viene ritentata
        # nello stesso run: il cursore passa oltre.
        ultima: tuple[datetime, uuid.UUID] | None = None
        for _ in range(PURGE_BATCH_SIZE):
            query = select(
                PendingObjectDeletion.id,
                PendingObjectDeletion.storage_key,
                PendingObjectDeletion.enqueued_at,
            ).where(PendingObjectDeletion.attempts < 10)
            if ultima is not None:
                ultimo_enqueued_at, ultimo_id = ultima
                query = query.where(
                    or_(
                        PendingObjectDeletion.enqueued_at > ultimo_enqueued_at,
                        and_(
                            PendingObjectDeletion.enqueued_at == ultimo_enqueued_at,
                            PendingObjectDeletion.id > ultimo_id,
                        ),
                    )
                )
            riga = session.execute(
                query.order_by(PendingObjectDeletion.enqueued_at, PendingObjectDeletion.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if riga is None:
                break
            row_id, storage_key, enqueued_at = riga
            ultima = (enqueued_at, row_id)
            try:
                s3.delete_object(Bucket=settings.notifyhub_s3_bucket, Key=storage_key)
                session.execute(
                    delete(PendingObjectDeletion).where(PendingObjectDeletion.id == row_id)
                )
                drained += 1
            except Exception as exc:  # noqa: BLE001
                session.execute(
                    update(PendingObjectDeletion)
                    .where(PendingObjectDeletion.id == row_id)
                    .values(attempts=PendingObjectDeletion.attempts + 1)
                )
                logger.error(
                    "drain_object_deletion_failed", storage_key=storage_key, error=str(exc)
                )
            # Commit per riga: un job interrotto a meta' batch non perde ne' le
            # cancellazioni gia' fatte ne' i tentativi contati. Cancellare l'oggetto
            # prima della riga resta l'ordine voluto (spec 6.5).
            session.commit()

    logger.info("drain_object_deletions_done", drained=drained)
    maintenance_job_runs_total.labels(job="drain_object_deletions", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.purge_orphan_objects")
def purge_orphan_objects() -> None:
    """Elimina gli oggetti del bucket piu vecchi di 24h senza riga
    corrispondente in notifications.storage_key: recupera i PUT riusciti con
    commit fallito (spec 6.5, 11)."""
    import boto3
    from botocore.config import Config

    from app.core.config import get_settings, s3_timeouts

    settings = get_settings()
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.notifyhub_s3_endpoint,
        aws_access_key_id=settings.notifyhub_s3_access_key,
        aws_secret_access_key=settings.notifyhub_s3_secret_key,
        region_name=settings.notifyhub_s3_region,
        # Stessi timeout del drain e del PUT: un MinIO lento non deve tenere il job appeso
        # per i 60 s di botocore a tentativo.
        config=Config(**s3_timeouts()),
    )

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    # notifications ha FORCE ROW LEVEL SECURITY e il ruolo notifyhub_app non ha
    # BYPASSRLS: una SELECT senza app.tenant_id impostato non torna NESSUNA riga,
    # non un errore. Leggere le chiavi note da una sessione senza contesto di
    # tenant produceva quindi un insieme vuoto e faceva considerare orfano OGNI
    # oggetto oltre le 24h, cancellando i payload delle notifiche ancora vive.
    # Va iterato tenant per tenant come tutti gli altri job (spec 5.3).
    known_keys: set[str] = set()
    for tenant_id in _all_tenant_ids():
        with tenant_session_sync(tenant_id) as session:
            rows = (
                session.execute(
                    select(Notification.storage_key).where(
                        Notification.tenant_id == tenant_id,
                        Notification.storage_key.isnot(None),
                    )
                )
                .scalars()
                .all()
            )
            known_keys.update(key for key in rows if key is not None)

    purged = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.notifyhub_s3_bucket):
        for obj in page.get("Contents", []):
            if obj["LastModified"] < cutoff and obj["Key"] not in known_keys:
                s3.delete_object(Bucket=settings.notifyhub_s3_bucket, Key=obj["Key"])
                purged += 1

    logger.info("purge_orphan_objects_done", purged=purged)
    maintenance_job_runs_total.labels(job="purge_orphan_objects", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.recompute_tenant_usage")
def recompute_tenant_usage() -> None:
    """Ricalcola lo spazio occupato per tenant e lo espone come metrica
    Prometheus (F7): alimenta il controllo di max_storage_bytes fatto dal vivo
    in app.services.quota, senza introdurre una colonna di cache non prevista
    dallo schema della spec. notifications ha FORCE ROW LEVEL SECURITY: senza
    app.tenant_id impostato la policy non lascia passare nessuna riga, quindi
    va iterato tenant per tenant come tutti gli altri job (spec 5.3)."""
    from app.core.metrics import tenant_storage_bytes

    for tenant_id in _all_tenant_ids():
        with tenant_session_sync(tenant_id) as session:
            total_bytes = session.execute(
                select(func.coalesce(func.sum(Notification.content_size), 0)).where(
                    Notification.tenant_id == tenant_id
                )
            ).scalar_one()
        tenant_storage_bytes.labels(tenant_id=str(tenant_id)).set(total_bytes)

    maintenance_job_runs_total.labels(job="recompute_tenant_usage", outcome="success").inc()


# --- sorveglianza dell'attesa ------------------------------------------------
# Job #8: l'unico che non reagisce a qualcosa che e' arrivato, ma al fatto che
# non e' arrivato niente. Vedi app/services/surveillance.py per il calcolo e la
# migrazione 0012 per le colonne.

CONTENT_PREVIEW_CHARS = 4096


def _synthetic_notification(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    receiver: Receiver,
    content: str,
    severity: Severity,
    source: SeveritySource,
    now: datetime,
) -> list[uuid.UUID]:
    """Notifica generata dal server, non inviata da nessuno.

    Nasce come una notifica normale (inline, `unread`, visibile in elenco e in
    dettaglio) e passa dallo stesso instradamento per severity: l'allarme di
    assenza deve poter arrivare sui canali configurati esattamente come un
    messaggio vero. `source_ip` resta NULL perche' non c'e' nessun mittente, e
    `metadata.generated_by` dice chi l'ha scritta.
    """
    notification = Notification(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        receiver_id=receiver.id,
        storage_backend="inline",
        content=content,
        storage_key=None,
        content_preview=content[:CONTENT_PREVIEW_CHARS],
        content_size=len(content.encode("utf-8")),
        content_normalized=False,
        severity=severity,
        severity_source=source,
        matched_pattern=None,
        duration_ms=None,
        exit_code=None,
        status=NotificationStatus.UNREAD,
        received_at=now,
        source_ip=None,
        meta={"generated_by": "expected_schedule", "kind": source.value},
    )
    session.add(notification)
    session.flush()

    return create_deliveries_for_notification_sync(
        session,
        tenant_id=tenant_id,
        group_id=receiver.group_id,
        receiver_id=receiver.id,
        notification_id=notification.id,
        severity=severity,
    )


@celery_app.task(name="app.tasks.maintenance.check_expected_schedules")
def check_expected_schedules() -> None:
    """Dead man's switch dei receiver sorvegliati (spec 11, job 8).

    Per ogni receiver attivo con una politica di attesa: se l'invio non e'
    arrivato entro la scadenza genera una notifica di assenza, una sola, e la
    riarma quando torna un invio vero, con una notifica di rientro `info`.

    Gira su tenant attivi: un tenant sospeso non riceve piu' ingestion, quindi
    sarebbe in assenza per definizione e allarmerebbe ogni minuto per sempre.
    """
    now = datetime.now(UTC)
    with sync_session_factory() as session:
        tenants = [
            row[0]
            for row in session.execute(
                select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
            ).all()
        ]

    missing_total = 0
    recovered_total = 0

    for tenant_id in tenants:
        pending: list[uuid.UUID] = []
        try:
            with tenant_session_sync(tenant_id) as session:
                # Ordine dei lock: prima il tenant, poi i receiver, come in
                # enforce_tenant_quotas. Con l'ordine inverso questo job teneva i
                # receiver e chiedeva il tenant (FK delle notifiche) mentre
                # un'ingestion con quota teneva il tenant e chiedeva un receiver.
                # FOR NO KEY UPDATE: confligge con il FOR UPDATE dell'ingestion con
                # quota, ma non con il FOR KEY SHARE che ogni INSERT prende via FK.
                session.execute(
                    select(Tenant.id).where(Tenant.id == tenant_id).with_for_update(key_share=True)
                )
                receivers = (
                    session.execute(
                        select(Receiver)
                        .where(
                            Receiver.tenant_id == tenant_id,
                            Receiver.missing_severity.isnot(None),
                            Receiver.status == ReceiverStatus.ACTIVE,
                        )
                        .with_for_update(skip_locked=True)
                    )
                    .scalars()
                    .all()
                )
                if not receivers:
                    continue

                group_names = {
                    row[0]: row[1]
                    for row in session.execute(
                        select(Group.id, Group.name).where(
                            Group.tenant_id == tenant_id,
                            Group.id.in_({r.group_id for r in receivers}),
                        )
                    ).all()
                }

                for receiver in receivers:
                    schedule = schedule_from_receiver(receiver)
                    if schedule is None:
                        continue
                    group_name = group_names.get(receiver.group_id, "?")

                    # Rientro: e' arrivato un invio vero DOPO l'allarme. Si valuta
                    # prima dell'assenza, cosi' un receiver tornato attivo non resta
                    # segnalato per un altro giro.
                    if (
                        receiver.missing_alerted_at is not None
                        and receiver.last_notification_at is not None
                        and receiver.last_notification_at > receiver.missing_alerted_at
                    ):
                        pending.extend(
                            _synthetic_notification(
                                session,
                                tenant_id=tenant_id,
                                receiver=receiver,
                                content=recovered_content(
                                    receiver_name=receiver.name,
                                    group_name=group_name,
                                    schedule=schedule,
                                    missing_alerted_at=receiver.missing_alerted_at,
                                    last_notification_at=receiver.last_notification_at,
                                ),
                                severity=Severity.INFO,
                                source=SeveritySource.RECOVERED,
                                now=now,
                            )
                        )
                        receiver.missing_alerted_at = None
                        recovered_total += 1
                        logger.info(
                            "expected_schedule_recovered",
                            tenant_id=str(tenant_id),
                            receiver_id=str(receiver.id),
                        )
                        continue

                    # Assenza: una sola notifica finche' non torna un invio vero.
                    if receiver.missing_alerted_at is not None:
                        continue

                    reference = reference_instant(receiver)
                    if reference is None:
                        continue

                    try:
                        deadline = alert_deadline(schedule, reference=reference)
                    except InvalidScheduleError as exc:
                        # Senza questa protezione un solo receiver con cron o fuso non
                        # calcolabile faceva morire il job a ogni giro, spegnendo la
                        # sorveglianza di TUTTI i tenant in silenzio.
                        logger.warning(
                            "expected_schedule_invalid",
                            tenant_id=str(tenant_id),
                            receiver_id=str(receiver.id),
                            slug=receiver.slug,
                            error=str(exc),
                        )
                        continue
                    if now <= deadline:
                        continue

                    assert receiver.missing_severity is not None
                    pending.extend(
                        _synthetic_notification(
                            session,
                            tenant_id=tenant_id,
                            receiver=receiver,
                            content=missing_content(
                                receiver_name=receiver.name,
                                group_name=group_name,
                                schedule=schedule,
                                last_notification_at=receiver.last_notification_at,
                                last_start_at=receiver.last_start_at,
                                expected_since=receiver.expected_since,
                                deadline=deadline,
                                now=now,
                            ),
                            severity=receiver.missing_severity,
                            source=SeveritySource.MISSING,
                            now=now,
                        )
                    )
                    receiver.missing_alerted_at = now
                    missing_total += 1
                    logger.warning(
                        "expected_schedule_missing",
                        tenant_id=str(tenant_id),
                        receiver_id=str(receiver.id),
                        slug=receiver.slug,
                        deadline=deadline.isoformat(),
                    )
        except Exception as exc:  # noqa: BLE001
            # Un tenant che fallisce (deadlock, errore DB) non deve fermare la
            # sorveglianza di tutti gli altri: il suo rollback annulla anche le
            # notifiche di assenza gia' preparate, e il giro dopo le riprova.
            logger.error(
                "expected_schedule_tenant_failed",
                tenant_id=str(tenant_id),
                error=type(exc).__name__,
            )
            pending.clear()
            continue

        # Accodamento fuori dalla transazione: commit-poi-enqueue come
        # nell'ingestion (spec 8.3). Se il processo muore qui le righe restano
        # `pending` e le ripesca reconcile_deliveries. Un broker che rifiuta un
        # messaggio non deve fermare i tenant successivi di questo giro: la riga e'
        # gia committata e il giro dopo o reconcile la riprende.
        for delivery_id in pending:
            try:
                enqueue_delivery(str(delivery_id), str(tenant_id))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "expected_schedule_enqueue_failed",
                    tenant_id=str(tenant_id),
                    delivery_id=str(delivery_id),
                    exc_info=True,
                )

    logger.info("check_expected_schedules_done", missing=missing_total, recovered=recovered_total)
    maintenance_job_runs_total.labels(job="check_expected_schedules", outcome="success").inc()
