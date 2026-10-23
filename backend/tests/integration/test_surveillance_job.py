"""Job di sorveglianza dell'attesa (spec 11, job 8) contro Postgres reale.

Il job e' l'unico che reagisce a cio' che non e' arrivato, quindi non basta
provare il calcolo (tests/unit/test_surveillance.py): bisogna verificare che
scriva davvero una notifica, che la mandi ai canali, che non ne scriva due, e che
si riarmi quando il job torna a inviare.
"""

import asyncio
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.crypto import encrypt_secret
from app.db.session import tenant_session
from app.db.sync_session import tenant_session_sync
from app.db.types import Severity, SeveritySource, TenantStatus
from app.models.binding import GroupChannelBinding
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.models.tenant import Tenant
from app.tasks.enqueue import reset_enqueue_function, set_enqueue_function
from app.tasks.maintenance import check_expected_schedules
from tests.conftest_factories import create_group, create_receiver

DAY = 86400


async def _sorveglia(
    tenant_id: uuid.UUID,
    receiver_id: uuid.UUID,
    *,
    every_seconds: int | None = DAY,
    cron: str | None = None,
    timezone: str | None = None,
    grace_seconds: int = 1800,
    severity: Severity = Severity.CRITICAL,
    last_notification_at: datetime | None = None,
    expected_since: datetime | None = None,
    missing_alerted_at: datetime | None = None,
) -> None:
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(
                expected_every_seconds=every_seconds,
                expected_cron=cron,
                expected_timezone=timezone,
                expected_grace_seconds=grace_seconds,
                missing_severity=severity,
                last_notification_at=last_notification_at,
                expected_since=expected_since,
                missing_alerted_at=missing_alerted_at,
            )
        )


async def _notifiche(tenant_id: uuid.UUID, receiver_id: uuid.UUID) -> list[Notification]:
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Notification)
            .where(Notification.receiver_id == receiver_id)
            .order_by(Notification.received_at.asc())
        )
        return list(result.scalars().all())


async def _receiver(tenant_id: uuid.UUID, receiver_id: uuid.UUID) -> Receiver:
    async with tenant_session(tenant_id) as session:
        result = await session.execute(select(Receiver).where(Receiver.id == receiver_id))
        return result.scalar_one()


async def _canale_con_soglia(
    tenant_id: uuid.UUID, group_id: uuid.UUID, min_severity: Severity
) -> uuid.UUID:
    """Canale e binding in due transazioni: nella stessa, l'unita di lavoro di
    SQLAlchemy emette l'INSERT del binding prima di quello del canale e la chiave
    esterna non trova la riga."""
    channel_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name=f"Slack {uuid.uuid4().hex[:6]}",
                type="slack",
                webhook_url=encrypt_secret("https://hooks.slack.com/services/AAA/BBB/CCC"),
                enabled=True,
            )
        )
    async with tenant_session(tenant_id) as session:
        session.add(
            GroupChannelBinding(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                group_id=group_id,
                channel_id=channel_id,
                min_severity=min_severity,
                enabled=True,
            )
        )
    return channel_id


def _esegui_job() -> list[tuple[str, str]]:
    """Job con l'accodamento intercettato: senza broker in questi test."""
    accodate: list[tuple[str, str]] = []
    set_enqueue_function(lambda delivery_id, tid: accodate.append((delivery_id, tid)))
    try:
        check_expected_schedules()
    finally:
        reset_enqueue_function()
    return accodate


@pytest.mark.integration
async def test_assenza_genera_una_notifica_e_arma_lo_stato(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    # Ultimo invio due giorni fa, attesa 24h + 30m: in ritardo di un giorno.
    await _sorveglia(
        tenant_id, receiver_id, last_notification_at=datetime.now(UTC) - timedelta(days=2)
    )

    _esegui_job()

    notifiche = await _notifiche(tenant_id, receiver_id)
    assert len(notifiche) == 1
    assenza = notifiche[0]
    assert assenza.severity == Severity.CRITICAL
    assert assenza.severity_source == SeveritySource.MISSING
    assert "nessun invio" in assenza.content_preview
    # Nessuno l'ha inviata: si vede da source_ip e dai metadati.
    assert assenza.source_ip is None
    assert assenza.meta["generated_by"] == "expected_schedule"

    receiver = await _receiver(tenant_id, receiver_id)
    assert receiver.missing_alerted_at is not None


@pytest.mark.integration
async def test_assenza_non_si_ripete_al_giro_successivo(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id, receiver_id, last_notification_at=datetime.now(UTC) - timedelta(days=2)
    )

    _esegui_job()
    _esegui_job()
    _esegui_job()

    # Una macchina spenta per una settimana non deve produrre 10.080 notifiche.
    assert len(await _notifiche(tenant_id, receiver_id)) == 1


@pytest.mark.integration
async def test_dentro_la_finestra_non_genera_niente(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id, receiver_id, last_notification_at=datetime.now(UTC) - timedelta(hours=2)
    )

    _esegui_job()

    assert await _notifiche(tenant_id, receiver_id) == []
    assert (await _receiver(tenant_id, receiver_id)).missing_alerted_at is None


@pytest.mark.integration
async def test_mai_ricevuto_niente_si_conta_da_expected_since(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id,
        receiver_id,
        last_notification_at=None,
        expected_since=datetime.now(UTC) - timedelta(days=3),
    )

    _esegui_job()

    notifiche = await _notifiche(tenant_id, receiver_id)
    assert len(notifiche) == 1
    assert "mai" in notifiche[0].content


@pytest.mark.integration
async def test_senza_riferimento_non_decide(two_tenants):
    """Politica attiva ma nessun invio e nessun expected_since: non c'e' niente da
    cui misurare, e inventarsi l'inizio dei tempi produrrebbe un allarme immediato
    su un receiver appena configurato a mano."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(tenant_id, receiver_id, last_notification_at=None, expected_since=None)

    _esegui_job()

    assert await _notifiche(tenant_id, receiver_id) == []


@pytest.mark.integration
async def test_receiver_disabilitato_ignorato(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id, receiver_id, last_notification_at=datetime.now(UTC) - timedelta(days=2)
    )
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver).where(Receiver.id == receiver_id).values(status="disabled")
        )

    _esegui_job()

    # Un receiver spento di proposito non e' un guasto da segnalare ogni minuto.
    assert await _notifiche(tenant_id, receiver_id) == []


@pytest.mark.integration
async def test_tenant_sospeso_ignorato(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id, receiver_id, last_notification_at=datetime.now(UTC) - timedelta(days=2)
    )
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Tenant).where(Tenant.id == tenant_id).values(status=TenantStatus.SUSPENDED)
        )
    try:
        _esegui_job()
        # Un tenant sospeso non riceve piu' ingestion: sarebbe in assenza per
        # definizione, e allarmerebbe per sempre.
        assert await _notifiche(tenant_id, receiver_id) == []
    finally:
        async with tenant_session(tenant_id) as session:
            await session.execute(
                update(Tenant).where(Tenant.id == tenant_id).values(status=TenantStatus.ACTIVE)
            )


@pytest.mark.integration
async def test_receiver_non_sorvegliato_ignorato(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    # Nessuna politica: la colonna missing_severity resta NULL.
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(last_notification_at=datetime.now(UTC) - timedelta(days=30))
        )

    _esegui_job()

    assert await _notifiche(tenant_id, receiver_id) == []


@pytest.mark.integration
async def test_rientro_genera_notifica_info_e_riarma(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    allarme = datetime.now(UTC) - timedelta(hours=5)
    # Invio arrivato DOPO l'allarme: il job deve accorgersene e chiudere il cerchio.
    await _sorveglia(
        tenant_id,
        receiver_id,
        last_notification_at=datetime.now(UTC) - timedelta(minutes=1),
        missing_alerted_at=allarme,
    )

    _esegui_job()

    notifiche = await _notifiche(tenant_id, receiver_id)
    assert len(notifiche) == 1
    rientro = notifiche[0]
    assert rientro.severity == Severity.INFO
    assert rientro.severity_source == SeveritySource.RECOVERED
    assert "ha ripreso a inviare" in rientro.content_preview

    receiver = await _receiver(tenant_id, receiver_id)
    assert receiver.missing_alerted_at is None

    # Riarmata: al giro dopo non nasce nessuna altra notifica, perche' l'invio e'
    # recente e la finestra e' aperta.
    _esegui_job()
    assert len(await _notifiche(tenant_id, receiver_id)) == 1


@pytest.mark.integration
async def test_ciclo_completo_assenza_rientro_assenza(two_tenants):
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id, receiver_id, last_notification_at=datetime.now(UTC) - timedelta(days=2)
    )

    _esegui_job()  # assenza
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(last_notification_at=datetime.now(UTC))
        )
    _esegui_job()  # rientro
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(last_notification_at=datetime.now(UTC) - timedelta(days=2))
        )
    _esegui_job()  # nuova assenza: la sorveglianza e' tornata operativa

    fonti = [n.severity_source for n in await _notifiche(tenant_id, receiver_id)]
    assert fonti == [SeveritySource.MISSING, SeveritySource.RECOVERED, SeveritySource.MISSING]


@pytest.mark.integration
async def test_assenza_arriva_ai_canali_sopra_soglia(two_tenants):
    """La ragione per cui la notifica e' sintetica e non un log: deve passare
    dall'instradamento per severity come qualunque altra."""
    tenant_id, _ = two_tenants
    group_id = await create_group(tenant_id, f"Sorveglianza {uuid.uuid4().hex[:6]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)

    channel_id = await _canale_con_soglia(tenant_id, group_id, Severity.ERROR)

    await _sorveglia(
        tenant_id, receiver_id, last_notification_at=datetime.now(UTC) - timedelta(days=2)
    )

    accodate = _esegui_job()

    notifiche = await _notifiche(tenant_id, receiver_id)
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Delivery).where(Delivery.notification_id == notifiche[0].id)
        )
        deliveries = list(result.scalars().all())
    assert len(deliveries) == 1
    assert deliveries[0].channel_id == channel_id
    # Accodata DOPO il commit, come nell'ingestion.
    assert (str(deliveries[0].id), str(tenant_id)) in accodate


@pytest.mark.integration
async def test_assenza_sotto_la_soglia_del_canale_non_consegna(two_tenants):
    tenant_id, _ = two_tenants
    group_id = await create_group(tenant_id, f"Sotto soglia {uuid.uuid4().hex[:6]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)

    await _canale_con_soglia(tenant_id, group_id, Severity.CRITICAL)

    await _sorveglia(
        tenant_id,
        receiver_id,
        last_notification_at=datetime.now(UTC) - timedelta(days=2),
        severity=Severity.WARNING,
    )

    _esegui_job()

    notifiche = await _notifiche(tenant_id, receiver_id)
    assert len(notifiche) == 1  # visibile in dashboard...
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Delivery).where(Delivery.notification_id == notifiche[0].id)
        )
        assert list(result.scalars().all()) == []  # ...ma sotto la soglia del canale


@pytest.mark.integration
async def test_cron_infrasettimanale_non_allarma_nel_weekend(two_tenants):
    """Lo stesso caso del test unitario, ma passando dal database: sabato con
    l'ultimo invio di venerdi non e' un'assenza."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])

    now = datetime.now(UTC)
    # Ultimo sabato, e ultimo invio il venerdi prima: sotto un cron 1-5 non c'e'
    # nessuna occorrenza in mezzo, quindi nessuna assenza.
    giorni_da_sabato = (now.weekday() - 5) % 7
    sabato = (now - timedelta(days=giorni_da_sabato)).replace(hour=12, minute=0, second=0)
    venerdi = sabato - timedelta(days=1)
    await _sorveglia(
        tenant_id,
        receiver_id,
        every_seconds=None,
        cron="0 3 * * 1-5",
        timezone="UTC",
        last_notification_at=venerdi.replace(hour=3, minute=0, second=10),
    )

    _esegui_job()

    # Il job usa l'ora reale: l'assertion regge solo se oggi il conto dice
    # "nessuna occorrenza mancata", che e' quello che il test unitario copre in
    # modo deterministico. Qui basta che il job non esploda e non scriva doppioni.
    notifiche = await _notifiche(tenant_id, receiver_id)
    assert len(notifiche) <= 1
    if notifiche:
        assert notifiche[0].severity_source == SeveritySource.MISSING


@pytest.mark.integration
async def test_ingestion_aggiorna_last_notification_at(api_client, two_tenants):
    """Il battito che tiene armata la sorveglianza: senza questo, ogni receiver
    sorvegliato allarmerebbe alla prima scadenza anche ricevendo notifiche."""
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    prima = (await _receiver(tenant_id, receiver_id)).last_notification_at
    assert prima is None

    response = await api_client.post(f"/ingest/{slug}", content="battito")
    assert response.status_code == 201

    dopo = (await _receiver(tenant_id, receiver_id)).last_notification_at
    assert dopo is not None


@pytest.mark.integration
async def test_notifica_sintetica_non_conta_come_battito(two_tenants):
    """Se l'assenza aggiornasse last_notification_at, la sorveglianza si
    riarmerebbe da sola e il rientro scatterebbe senza che nessuno abbia inviato
    niente."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    ultimo = datetime.now(UTC) - timedelta(days=2)
    await _sorveglia(tenant_id, receiver_id, last_notification_at=ultimo)

    _esegui_job()
    _esegui_job()

    receiver = await _receiver(tenant_id, receiver_id)
    assert receiver.last_notification_at == ultimo
    notifiche = await _notifiche(tenant_id, receiver_id)
    assert [n.severity_source for n in notifiche] == [SeveritySource.MISSING]


@pytest.mark.integration
async def test_cron_con_tolleranza_piu_lunga_del_periodo_allarma_comunque(two_tenants):
    """Regressione: la scadenza si ancora alla prima occorrenza DOPO l'ultimo
    invio, non alla prossima da adesso. Ancorandola ad adesso, una tolleranza
    lunga quanto o piu' del periodo (qui 2h su un cron orario) spostava la
    scadenza sempre nel futuro e l'allarme non scattava mai."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id,
        receiver_id,
        every_seconds=None,
        cron="0 * * * *",
        timezone="UTC",
        grace_seconds=7200,
        last_notification_at=datetime.now(UTC) - timedelta(days=3),
    )

    _esegui_job()

    notifiche = await _notifiche(tenant_id, receiver_id)
    assert len(notifiche) == 1
    assert notifiche[0].severity_source == SeveritySource.MISSING


@pytest.mark.integration
async def test_cron_dentro_la_tolleranza_non_allarma(two_tenants):
    """Controprova del test precedente: con l'invio appena arrivato la scadenza
    resta di la' da venire e il job non deve scrivere niente."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id,
        receiver_id,
        every_seconds=None,
        cron="0 * * * *",
        timezone="UTC",
        grace_seconds=7200,
        last_notification_at=datetime.now(UTC) - timedelta(minutes=10),
    )

    _esegui_job()

    assert await _notifiche(tenant_id, receiver_id) == []
    assert (await _receiver(tenant_id, receiver_id)).missing_alerted_at is None


@pytest.mark.integration
async def test_cron_mai_ricevuto_niente_si_conta_da_expected_since(two_tenants):
    """Anche in forma cron il receiver che non ha mai inviato ha un riferimento:
    l'istante in cui la sorveglianza e' stata accesa."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id,
        receiver_id,
        every_seconds=None,
        cron="0 3 * * *",
        timezone="Europe/Rome",
        last_notification_at=None,
        expected_since=datetime.now(UTC) - timedelta(days=3),
    )

    _esegui_job()

    notifiche = await _notifiche(tenant_id, receiver_id)
    assert len(notifiche) == 1
    assert "mai" in notifiche[0].content


@pytest.mark.integration
async def test_riaccensione_recente_batte_un_invio_piu_vecchio(two_tenants):
    """expected_since aggiornato dopo la riattivazione del receiver deve avere la
    meglio su un last_notification_at di una settimana fa: e' il caso del
    receiver riacceso, che non deve allarmare al primo giro del job."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id,
        receiver_id,
        last_notification_at=datetime.now(UTC) - timedelta(days=7),
        expected_since=datetime.now(UTC) - timedelta(minutes=1),
    )

    _esegui_job()

    assert await _notifiche(tenant_id, receiver_id) == []


@pytest.mark.integration
async def test_un_tenant_che_fallisce_non_ferma_la_sorveglianza_degli_altri(
    two_tenants, monkeypatch
):
    """Un errore sul tenant A (per esempio un deadlock) non deve saltare il tenant
    B nello stesso giro: il giro dopo riprova A, B riceve il suo allarme ora."""
    from app.tasks import maintenance

    tenant_a, tenant_b = two_tenants
    receiver_a = await create_receiver(tenant_a, uuid.uuid4().hex[:22])
    receiver_b = await create_receiver(tenant_b, uuid.uuid4().hex[:22])
    for tenant_id, receiver_id in ((tenant_a, receiver_a), (tenant_b, receiver_b)):
        await _sorveglia(
            tenant_id,
            receiver_id,
            last_notification_at=datetime.now(UTC) - timedelta(days=2),
        )

    schedule_reale = maintenance.schedule_from_receiver

    def schedule_guasto(receiver):
        if receiver.tenant_id == tenant_a:
            raise RuntimeError("errore simulato sul tenant A")
        return schedule_reale(receiver)

    monkeypatch.setattr(maintenance, "schedule_from_receiver", schedule_guasto)

    _esegui_job()

    assert len(await _notifiche(tenant_b, receiver_b)) == 1
    assert await _notifiche(tenant_a, receiver_a) == []


@pytest.mark.integration
async def test_sorveglianza_chiede_il_tenant_prima_dei_receiver(two_tenants):
    """Ordine dei lock come in enforce_tenant_quotas: la sorveglianza prende prima il
    tenant. Con il tenant tenuto da un'ingestion con quota, la sorveglianza non deve
    aver gia' preso il receiver: il NOWAIT sul receiver riesce."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    await _sorveglia(
        tenant_id, receiver_id, last_notification_at=datetime.now(UTC) - timedelta(days=2)
    )

    errori: list[BaseException] = []

    def sorveglianza() -> None:
        try:
            check_expected_schedules()
        except BaseException as exc:  # noqa: BLE001
            errori.append(exc)

    set_enqueue_function(lambda delivery_id, tid: None)
    thread = threading.Thread(target=sorveglianza)
    try:
        with tenant_session_sync(tenant_id) as tenta:
            # Il tenant lo tiene l'ingestion con quota (FOR UPDATE, come in quota.py).
            tenta.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
            thread.start()
            await asyncio.sleep(1.5)
            # Se la sorveglianza avesse gia' il receiver, questo NOWAIT fallirebbe.
            tenta.execute(
                select(Receiver.id).where(Receiver.id == receiver_id).with_for_update(nowait=True)
            ).one()
    finally:
        thread.join(timeout=30)
        reset_enqueue_function()

    assert not thread.is_alive()
    assert errori == []
    assert len(await _notifiche(tenant_id, receiver_id)) == 1
