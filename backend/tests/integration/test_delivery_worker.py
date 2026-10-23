"""Test del task Celery dispatch_delivery (spec 8.2): macchina a stati e
gestione degli esiti del webhook. Il task viene chiamato direttamente (non
via broker): Celery permette di invocare un task come funzione normale."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from app.core.crypto import encrypt_secret
from app.db.session import tenant_session
from app.db.types import DeliveryStatus, Severity
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.tasks.delivery import dispatch_delivery
from tests.conftest_factories import create_receiver

WEBHOOK_URL = "https://hooks.slack.com/services/T0/B0/X0"


async def _setup_delivery(
    tenant_id: uuid.UUID, status: str = "pending"
) -> tuple[uuid.UUID, uuid.UUID]:
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    channel_id = uuid.uuid4()
    notification_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    async with tenant_session(tenant_id) as session:
        # flush esplicito fra ogni insert: l'ordinamento automatico dello unit
        # of work non va dato per scontato quando le entita non sono legate
        # da relationship() ORM, solo da ForeignKey a livello di colonna.
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name="Slack #ops",
                type="slack",
                webhook_url=encrypt_secret(WEBHOOK_URL),
                enabled=True,
            )
        )
        await session.flush()

        session.add(
            Notification(
                id=notification_id,
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                storage_backend="inline",
                content="Backup FALLITO",
                storage_key=None,
                content_preview="Backup FALLITO",
                content_size=len("Backup FALLITO"),
                content_normalized=False,
                severity=Severity.ERROR,
                severity_source="receiver_default",
                status="unread",
                received_at=datetime.now(UTC),
                source_ip=None,
                meta={},
            )
        )
        await session.flush()

        session.add(
            Delivery(
                id=delivery_id,
                tenant_id=tenant_id,
                notification_id=notification_id,
                channel_id=channel_id,
                status=status,
                attempts=0,
                next_attempt_at=datetime.now(UTC),
            )
        )
        await session.flush()

    return delivery_id, channel_id


@pytest.mark.integration
@respx.mock
async def test_2xx_marca_sent(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.SENT
        assert delivery.sent_at is not None
        assert delivery.response_code == 200


@pytest.mark.integration
@respx.mock
async def test_4xx_non_429_marca_dead_senza_retry(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, channel_id = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(410))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.DEAD
        assert delivery.attempts == 0  # morta subito, non e un retry
        channel = await session.get(DeliveryChannel, channel_id)
        assert channel.last_error is not None


@pytest.mark.integration
@respx.mock
async def test_429_ripianifica_rispettando_retry_after(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "120"}))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 1


@pytest.mark.integration
@respx.mock
async def test_429_al_quinto_tentativo_diventa_dead(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "non-valido"})
    )

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        delivery.attempts = 4

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.DEAD
        assert delivery.attempts == 5


@pytest.mark.integration
@respx.mock
async def test_5xx_incrementa_attempts_e_ripianifica(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(503))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 1
        assert delivery.next_attempt_at is not None


@pytest.mark.integration
@respx.mock
async def test_5xx_dopo_5_tentativi_diventa_dead(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(503))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        delivery.attempts = 4

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.DEAD
        assert delivery.attempts == 5


@pytest.mark.integration
async def test_delivery_gia_sent_viene_ignorata(two_tenants):
    """Idempotenza del task: una delivery non piu pending/failed (per esempio
    perche un altro worker l'ha gia consumata) non viene rilavorata."""
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id, status="sent")

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.SENT
        assert delivery.attempts == 0


@pytest.mark.integration
async def test_canale_disabilitato_rende_terminale_la_delivery(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, channel_id = await _setup_delivery(tenant_id)
    async with tenant_session(tenant_id) as session:
        channel = await session.get(DeliveryChannel, channel_id)
        channel.enabled = False

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.DEAD
        assert delivery.last_error == "channel disabled before delivery"


# --- Review 2026-09 ------------------------------------------------------------


@pytest.mark.integration
async def test_webhook_non_decifrabile_rende_la_delivery_dead_con_la_causa(two_tenants):
    """Con NOTIFYHUB_SECRET_KEY cambiata la decifratura sollevava dentro la fase 1:
    rollback, riga di nuovo `pending`, reconcile che la riaccodava ogni 5 minuti
    per sempre, senza last_error ne' tentativi contati."""
    tenant_id, _ = two_tenants
    delivery_id, channel_id = await _setup_delivery(tenant_id)
    async with tenant_session(tenant_id) as session:
        channel = await session.get(DeliveryChannel, channel_id)
        channel.webhook_url = b"x" * 48  # cifrato con un'altra chiave: tag GCM non valido

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.DEAD
        assert delivery.last_error is not None
        assert "decryption" in delivery.last_error
        channel = await session.get(DeliveryChannel, channel_id)
        assert channel.last_error is not None


@pytest.mark.integration
async def test_esito_di_un_tentativo_orfano_non_sovrascrive_lo_stato(two_tenants, monkeypatch):
    """Fra la fase 1 e la fase 3 reconcile puo' riprendersi una riga rimasta
    `sending` troppo a lungo e riaccodarla: l'esito del vecchio tentativo non deve
    scavalcare lo stato del nuovo proprietario."""
    from app.db.sync_session import tenant_session_sync
    from app.outbound.sender import WebhookResult
    from app.tasks import delivery as delivery_module

    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)

    def invio_lento(*_args, **_kwargs):
        # Simula reconcile durante la chiamata di rete.
        with tenant_session_sync(tenant_id) as session:
            riga = session.get(Delivery, delivery_id)
            riga.status = DeliveryStatus.FAILED
            riga.locked_at = None
        return WebhookResult(ok=True, status_code=200, retry_after=None, error=None)

    monkeypatch.setattr(delivery_module, "send_webhook_sync", invio_lento)

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.sent_at is None


@pytest.mark.integration
@respx.mock
async def test_errore_di_rete_non_espone_il_segreto_del_webhook(two_tenants):
    """Il testo delle eccezioni httpx contiene l'URL completo: finiva in
    last_error, che la dashboard mostra anche ai member."""
    tenant_id, _ = two_tenants
    delivery_id, channel_id = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(
        side_effect=httpx.ConnectError(f"connessione fallita verso {WEBHOOK_URL}")
    )

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        channel = await session.get(DeliveryChannel, channel_id)
        for testo in (delivery.last_error, channel.last_error):
            assert testo is not None
            assert "/services/T0/B0/X0" not in testo
            assert "ConnectError" in testo


@pytest.mark.integration
@respx.mock
async def test_failed_non_ancora_scaduta_non_viene_rispedita(two_tenants):
    """Un duplicato accodato prima della scadenza del backoff (reconcile ogni 5
    minuti) non deve colpire il webhook: la delivery resta com'e'."""
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id, status="failed")
    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        delivery.attempts = 1
        delivery.next_attempt_at = datetime.now(UTC) + timedelta(seconds=300)
    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    assert not route.called
    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 1


@pytest.mark.integration
@respx.mock
async def test_failed_scaduta_viene_rispedita(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id, status="failed")
    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        delivery.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.SENT


@pytest.mark.integration
@respx.mock
async def test_429_con_retry_after_enorme_ripianifica_senza_crash(two_tenants):
    """Un Retry-After fuori scala non fa crashare phase 3 (overflow della data):
    la delivery torna `failed` con un prossimo tentativo finito."""
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "300000000000"})
    )

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 1
        assert delivery.next_attempt_at <= datetime.now(UTC) + timedelta(hours=7)
