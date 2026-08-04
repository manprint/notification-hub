"""Job Celery Beat di manutenzione (spec 11). Girano con il ruolo
notifyhub_app, senza privilegi di bypass: quelli che toccano dati di tenant
iterano i tenant e impostano app.tenant_id per ciascuno (spec 5.3)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
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
from app.models.channel import DeliveryChannel
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
    ExpectedSchedule,
    alert_deadline,
    missing_content,
    recovered_content,
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
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        deleted_total = 0
        with tenant_session_sync(tenant_id) as session:
            while True:
                ids = (
                    session.execute(
                        select(Notification.id)
                        .where(
                            Notification.tenant_id == tenant_id, Notification.received_at < cutoff
                        )
                        .limit(PURGE_BATCH_SIZE)
                    )
                    .scalars()
                    .all()
                )
                if not ids:
                    break
                session.execute(delete(Notification).where(Notification.id.in_(ids)))
                session.commit()
                deleted_total += len(ids)
                if len(ids) < PURGE_BATCH_SIZE:
                    break
        logger.info("purge_notifications_done", tenant_id=str(tenant_id), deleted=deleted_total)
    maintenance_job_runs_total.labels(job="purge_notifications", outcome="success").inc()


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
    """Elimina refresh token scaduti/revocati e inviti scaduti (spec 11).
    Tabelle scoped-per-tenant: itera i tenant come tutto il resto."""
    now = datetime.now(UTC)
    for tenant_id in _all_tenant_ids():
        with tenant_session_sync(tenant_id) as session:
            session.execute(
                delete(RefreshToken).where(
                    RefreshToken.tenant_id == tenant_id,
                    (RefreshToken.expires_at < now) | (RefreshToken.revoked_at.isnot(None)),
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
            # Solo le delivery verso canali attivi: dispatch_delivery esce
            # subito su un canale disabilitato lasciando la riga `pending`, e
            # senza questo filtro il job la riaccodava a ogni giro, per sempre.
            enabled_channels = select(DeliveryChannel.id).where(
                DeliveryChannel.tenant_id == tenant_id,
                DeliveryChannel.enabled.is_(True),
            )
            due = (
                session.execute(
                    select(Delivery.id).where(
                        Delivery.tenant_id == tenant_id,
                        Delivery.status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
                        Delivery.next_attempt_at <= now,
                        Delivery.channel_id.in_(enabled_channels),
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

            for delivery_id in stuck:
                delivery = session.get(Delivery, delivery_id)
                if delivery is None:
                    continue
                delivery.status = DeliveryStatus.FAILED
                delivery.locked_at = None

        for delivery_id in list(due) + list(stuck):
            enqueue_delivery(str(delivery_id), str(tenant_id))
            requeued += 1

    logger.info("reconcile_deliveries_done", requeued=requeued)
    maintenance_job_runs_total.labels(job="reconcile_deliveries", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.drain_object_deletions")
def drain_object_deletions() -> None:
    """Svuota pending_object_deletions cancellando gli oggetti da MinIO (spec
    6.5, 11). Tabella fuori da RLS, nessun contesto di tenant necessario. Dopo
    10 tentativi falliti la riga resta e alimenta una metrica di allarme."""
    import boto3

    from app.core.config import get_settings

    settings = get_settings()
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.notifyhub_s3_endpoint,
        aws_access_key_id=settings.notifyhub_s3_access_key,
        aws_secret_access_key=settings.notifyhub_s3_secret_key,
        region_name=settings.notifyhub_s3_region,
    )

    with sync_session_factory() as session:
        rows = (
            session.execute(
                select(PendingObjectDeletion).where(PendingObjectDeletion.attempts < 10)
            )
            .scalars()
            .all()
        )

        drained = 0
        for row in rows:
            try:
                s3.delete_object(Bucket=settings.notifyhub_s3_bucket, Key=row.storage_key)
                session.delete(row)
                drained += 1
            except Exception as exc:  # noqa: BLE001
                row.attempts += 1
                logger.error(
                    "drain_object_deletion_failed", storage_key=row.storage_key, error=str(exc)
                )
        session.commit()

    logger.info("drain_object_deletions_done", drained=drained)
    maintenance_job_runs_total.labels(job="drain_object_deletions", outcome="success").inc()


@celery_app.task(name="app.tasks.maintenance.purge_orphan_objects")
def purge_orphan_objects() -> None:
    """Elimina gli oggetti del bucket piu vecchi di 24h senza riga
    corrispondente in notifications.storage_key: recupera i PUT riusciti con
    commit fallito (spec 6.5, 11)."""
    import boto3

    from app.core.config import get_settings

    settings = get_settings()
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.notifyhub_s3_endpoint,
        aws_access_key_id=settings.notifyhub_s3_access_key,
        aws_secret_access_key=settings.notifyhub_s3_secret_key,
        region_name=settings.notifyhub_s3_region,
    )

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    with sync_session_factory() as session:
        known_keys = set(
            session.execute(
                select(Notification.storage_key).where(Notification.storage_key.isnot(None))
            )
            .scalars()
            .all()
        )

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
    group_name: str,
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


def _reference_instant(receiver: Receiver, schedule: ExpectedSchedule) -> datetime | None:
    """Da quando si conta l'attesa: l'ultimo invio vero, oppure il momento in cui
    la politica e' entrata in vigore per un receiver che non ha mai ricevuto
    niente. Senza nessuno dei due non si puo' decidere e si lascia stare."""
    if receiver.last_notification_at is not None:
        return receiver.last_notification_at
    return receiver.expected_since


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
        with tenant_session_sync(tenant_id) as session:
            receivers = (
                session.execute(
                    select(Receiver).where(
                        Receiver.tenant_id == tenant_id,
                        Receiver.missing_severity.isnot(None),
                        Receiver.status == ReceiverStatus.ACTIVE,
                    )
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
                            group_name=group_name,
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

                reference = _reference_instant(receiver, schedule)
                if reference is None:
                    continue

                deadline = alert_deadline(schedule, reference=reference, now=now)
                if now <= deadline:
                    continue

                assert receiver.missing_severity is not None
                pending.extend(
                    _synthetic_notification(
                        session,
                        tenant_id=tenant_id,
                        receiver=receiver,
                        group_name=group_name,
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

        # Accodamento fuori dalla transazione: commit-poi-enqueue come
        # nell'ingestion (spec 8.3). Se il processo muore qui le righe restano
        # `pending` e le ripesca reconcile_deliveries.
        for delivery_id in pending:
            enqueue_delivery(str(delivery_id), str(tenant_id))

    logger.info("check_expected_schedules_done", missing=missing_total, recovered=recovered_total)
    maintenance_job_runs_total.labels(job="check_expected_schedules", outcome="success").inc()
