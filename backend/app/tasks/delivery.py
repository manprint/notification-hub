"""Task Celery che consuma l'outbox e invia i webhook (spec 8.2, 8.4).

Gira su un engine SQLAlchemy sincrono dedicato (app.db.sync_session): l'API
resta async, il worker no, per evitare un event loop per task.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.crypto import decrypt_secret
from app.core.logging import get_logger
from app.core.metrics import deliveries_total
from app.core.urls import configured_base_url
from app.db.sync_session import tenant_session_sync
from app.db.types import DeliveryStatus
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.outbound.sender import MAX_ATTEMPTS, calculate_retry_delay, send_webhook_sync
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.delivery.dispatch_delivery")
def dispatch_delivery(delivery_id: str, tenant_id: str) -> None:
    tid = uuid.UUID(tenant_id)
    did = uuid.UUID(delivery_id)

    # Fase 1: marca `sending` e legge quel che serve per formattare il
    # messaggio. Transazione breve: non tiene un lock durante la chiamata
    # di rete.
    with tenant_session_sync(tid) as session:
        delivery = session.get(Delivery, did)
        if delivery is None or delivery.status not in (
            DeliveryStatus.PENDING,
            DeliveryStatus.FAILED,
        ):
            logger.info("dispatch_delivery_skipped", delivery_id=delivery_id, reason="wrong_state")
            return

        channel = session.get(DeliveryChannel, delivery.channel_id)
        notification = session.get(Notification, delivery.notification_id)
        if channel is None or notification is None:
            delivery.status = DeliveryStatus.DEAD
            delivery.last_error = "channel or notification missing"
            return
        if not channel.enabled:
            logger.info(
                "dispatch_delivery_skipped", delivery_id=delivery_id, reason="channel_disabled"
            )
            return

        receiver = session.get(Receiver, notification.receiver_id)
        receiver_name = receiver.name if receiver else "receiver"
        # La soglia sta sul receiver, la durata sulla notifica: servono insieme
        # per dire nel messaggio non solo quanto e' durato, ma se era troppo.
        duration_threshold_seconds = receiver.duration_threshold_seconds if receiver else None

        delivery.status = DeliveryStatus.SENDING
        delivery.locked_at = datetime.now(UTC)
        session.flush()

        webhook_url = decrypt_secret(channel.webhook_url)
        channel_type = channel.type
        severity = notification.severity
        content_preview = notification.content_preview
        content_size = notification.content_size
        duration_ms = notification.duration_ms
        attempts_so_far = delivery.attempts
        # Nel worker non c'e' nessuna richiesta da cui dedurre l'origine: qui
        # l'unica autorita' e' NOTIFYHUB_PUBLIC_BASE_URL, normalizzata.
        notification_url = f"{configured_base_url()}/notifications/{notification.id}"

    # Fase 2: la chiamata di rete, FUORI dalla transazione.
    result = send_webhook_sync(
        channel_type,
        webhook_url,
        receiver_name=receiver_name,
        severity=severity,
        content_preview=content_preview,
        content_size=content_size,
        notification_url=notification_url,
        duration_ms=duration_ms,
        duration_threshold_seconds=duration_threshold_seconds,
    )

    # Fase 3: scrive l'esito in una nuova transazione (spec 8.2).
    with tenant_session_sync(tid) as session:
        delivery = session.get(Delivery, did)
        if delivery is None:
            logger.error("dispatch_delivery_vanished", delivery_id=delivery_id)
            return
        channel = session.get(DeliveryChannel, delivery.channel_id)
        now = datetime.now(UTC)

        if result.ok:
            delivery.status = DeliveryStatus.SENT
            delivery.sent_at = now
            delivery.response_code = result.status_code
            delivery.last_error = None
            if channel is not None:
                channel.last_success_at = now
            deliveries_total.labels(outcome="sent").inc()
            return

        if result.status_code == 429:
            delivery.status = DeliveryStatus.FAILED
            delivery.response_code = result.status_code
            delivery.last_error = result.error
            delivery.next_attempt_at = now + timedelta(seconds=result.retry_after or 60)
            deliveries_total.labels(outcome="rate_limited").inc()
            return

        if result.status_code is not None and 400 <= result.status_code < 500:
            # Webhook revocato o simile: morta subito, nessun retry (spec 8.2).
            delivery.status = DeliveryStatus.DEAD
            delivery.response_code = result.status_code
            delivery.last_error = result.error
            if channel is not None:
                channel.last_error_at = now
                channel.last_error = result.error
            deliveries_total.labels(outcome="dead").inc()
            return

        # 5xx o timeout: retry con backoff esponenziale + jitter.
        delivery.attempts = attempts_so_far + 1
        delivery.response_code = result.status_code
        delivery.last_error = result.error
        if channel is not None:
            channel.last_error_at = now
            channel.last_error = result.error

        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = DeliveryStatus.DEAD
            deliveries_total.labels(outcome="dead").inc()
        else:
            delivery.status = DeliveryStatus.FAILED
            delay = calculate_retry_delay(delivery.attempts)
            delivery.next_attempt_at = now + timedelta(seconds=delay)
            deliveries_total.labels(outcome="failed").inc()
