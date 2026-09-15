"""API della sorveglianza dell'attesa: configurazione, stato, visibilita'.

La configurazione ha quattro campi che devono stare insieme e due modi
alternativi di dichiarare l'attesa: e' il tipo di forma che si sbaglia, quindi il
422 deve dire quale pezzo manca invece di limitarsi a rifiutare.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.db.session import tenant_session
from app.db.types import Severity, SeveritySource
from app.models.notification import Notification
from app.models.receiver import Receiver

ATTESA_GIORNALIERA = {
    "expected_every_seconds": 86400,
    "expected_grace_seconds": 1800,
    "missing_severity": "critical",
}


async def _gruppo_e_receiver(api_client, headers, payload: dict | None = None):
    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Attesa {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    body = {"name": "backup notturno"}
    body.update(payload or {})
    receiver_resp = await api_client.post(
        f"/api/v1/groups/{group_id}/receivers", json=body, headers=headers
    )
    return group_id, receiver_resp


@pytest.mark.e2e
async def test_creazione_con_attesa_a_intervallo(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    assert resp.status_code == 201
    receiver = resp.json()
    assert receiver["expected_every_seconds"] == 86400
    assert receiver["missing_severity"] == "critical"
    # Il receiver appena creato non ha ricevuto niente: la finestra si conta da
    # adesso, e la scadenza e' fra 24h30m.
    assert receiver["expected_since"] is not None
    assert receiver["expected_deadline_at"] is not None
    assert receiver["expected_late"] is False


@pytest.mark.e2e
async def test_creazione_con_attesa_a_cron(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(
        api_client,
        headers,
        {
            "expected_cron": "0 3 * * 1-5",
            "expected_timezone": "Europe/Rome",
            "expected_grace_seconds": 900,
            "missing_severity": "error",
        },
    )
    assert resp.status_code == 201
    receiver = resp.json()
    assert receiver["expected_cron"] == "0 3 * * 1-5"
    assert receiver["expected_timezone"] == "Europe/Rome"
    assert receiver["expected_deadline_at"] is not None


@pytest.mark.e2e
async def test_senza_attesa_lo_stato_resta_vuoto(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers)
    receiver = resp.json()
    assert receiver["missing_severity"] is None
    assert receiver["expected_deadline_at"] is None
    assert receiver["expected_since"] is None


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("payload", "atteso_nel_messaggio"),
    [
        ({"expected_every_seconds": 86400}, "expected_grace_seconds"),
        ({"missing_severity": "critical"}, "expected_grace_seconds"),
        ({"expected_grace_seconds": 60, "missing_severity": "critical"}, "exactly one"),
        (
            {
                "expected_every_seconds": 86400,
                "expected_cron": "0 3 * * *",
                "expected_grace_seconds": 60,
                "missing_severity": "critical",
            },
            "not both",
        ),
        (
            {
                "expected_cron": "non un cron",
                "expected_grace_seconds": 60,
                "missing_severity": "critical",
            },
            "cron",
        ),
        (
            {
                "expected_cron": "0 3 * * * *",
                "expected_grace_seconds": 60,
                "missing_severity": "critical",
            },
            "5 campi",
        ),
        (
            {
                "expected_cron": "0 3 * * *",
                "expected_timezone": "Europa/Roma",
                "expected_grace_seconds": 60,
                "missing_severity": "critical",
            },
            "fuso orario sconosciuto",
        ),
        (
            {
                "expected_every_seconds": 86400,
                "expected_timezone": "UTC",
                "expected_grace_seconds": 60,
                "missing_severity": "critical",
            },
            "expected_timezone",
        ),
    ],
)
async def test_configurazione_incompleta_rifiutata_in_creazione(
    api_client, two_tenants, owner_token, payload, atteso_nel_messaggio
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, payload)
    assert resp.status_code == 422
    assert atteso_nel_messaggio in resp.text


@pytest.mark.e2e
async def test_patch_puo_toccare_un_solo_campo(api_client, two_tenants, owner_token):
    """Con la politica gia' attiva, cambiare solo la tolleranza e' legittimo: la
    coerenza si verifica sullo stato finale, non sul corpo della richiesta."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver_id = resp.json()["id"]

    patch = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}",
        json={"expected_grace_seconds": 3600},
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["expected_grace_seconds"] == 3600
    assert patch.json()["expected_every_seconds"] == 86400


@pytest.mark.e2e
async def test_patch_da_intervallo_a_cron(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver_id = resp.json()["id"]

    # Passare all'espressione cron richiede di azzerare l'intervallo: i due sono
    # due modi di dire la stessa cosa e non possono convivere.
    solo_cron = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}",
        json={"expected_cron": "0 3 * * *"},
        headers=headers,
    )
    assert solo_cron.status_code == 422
    assert "not both" in solo_cron.text

    ok = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}",
        json={"expected_every_seconds": None, "expected_cron": "0 3 * * *"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json()["expected_cron"] == "0 3 * * *"
    assert ok.json()["expected_every_seconds"] is None


@pytest.mark.e2e
async def test_patch_spegne_la_sorveglianza_e_pulisce_lo_stato(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver_id = resp.json()["id"]

    # Stato sporco come dopo un allarme vero.
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == uuid.UUID(receiver_id))
            .values(missing_alerted_at=datetime.now(UTC) - timedelta(days=1))
        )

    spenta = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}",
        json={
            "expected_every_seconds": None,
            "expected_grace_seconds": None,
            "missing_severity": None,
        },
        headers=headers,
    )
    assert spenta.status_code == 200
    body = spenta.json()
    assert body["missing_severity"] is None
    # Riaccendendola non si deve ereditare un allarme di ieri.
    assert body["missing_alerted_at"] is None
    assert body["expected_since"] is None
    assert body["expected_deadline_at"] is None


@pytest.mark.e2e
async def test_stato_in_ritardo_visibile_nel_dettaglio(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver_id = resp.json()["id"]

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == uuid.UUID(receiver_id))
            .values(
                last_notification_at=datetime.now(UTC) - timedelta(days=3),
                # Sorveglianza accesa da prima del silenzio: e' il caso in cui
                # il ritardo e' vero (reference_instant prende il piu' recente
                # dei due istanti).
                expected_since=datetime.now(UTC) - timedelta(days=10),
            )
        )

    detail = await api_client.get(f"/api/v1/receivers/{receiver_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["expected_late"] is True
    assert body["last_notification_at"] is not None


@pytest.mark.e2e
async def test_ingestion_aggiorna_lo_stato_esposto(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver = resp.json()
    assert receiver["last_notification_at"] is None

    ingest = await api_client.post(f"/ingest/{receiver['slug']}", content="battito")
    assert ingest.status_code == 201

    detail = await api_client.get(f"/api/v1/receivers/{receiver['id']}", headers=headers)
    assert detail.json()["last_notification_at"] is not None
    assert detail.json()["expected_late"] is False


@pytest.mark.e2e
async def test_notifiche_di_sorveglianza_visibili_e_filtrabili(
    api_client, two_tenants, owner_token
):
    """Il requisito che le rende utili: assenza e rientro si vedono nella sezione
    notifiche come tutte le altre, e si possono isolare col filtro sull'origine."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver = resp.json()
    receiver_id = uuid.UUID(receiver["id"])

    # Una notifica normale (via ingestion) e le due sintetiche, scritte come le
    # scrive il job.
    await api_client.post(f"/ingest/{receiver['slug']}", content="esecuzione riuscita")
    async with tenant_session(tenant_id) as session:
        for source, severity, testo in (
            (SeveritySource.MISSING, Severity.CRITICAL, "[notifyhub] nessun invio da backup"),
            (SeveritySource.RECOVERED, Severity.INFO, "[notifyhub] ha ripreso a inviare"),
        ):
            session.add(
                Notification(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    receiver_id=receiver_id,
                    storage_backend="inline",
                    content=testo,
                    content_preview=testo,
                    content_size=len(testo.encode()),
                    content_normalized=False,
                    severity=severity,
                    severity_source=source,
                    status="unread",
                    received_at=datetime.now(UTC),
                    source_ip=None,
                    meta={"generated_by": "expected_schedule"},
                )
            )

    tutte = await api_client.get(
        "/api/v1/notifications", params={"receiver_id": str(receiver_id)}, headers=headers
    )
    assert tutte.status_code == 200
    fonti = {n["severity_source"] for n in tutte.json()["notifications"]}
    assert {"missing", "recovered"} <= fonti

    solo_assenze = await api_client.get(
        "/api/v1/notifications",
        params={"receiver_id": str(receiver_id), "source": "missing"},
        headers=headers,
    )
    assert solo_assenze.status_code == 200
    elenco = solo_assenze.json()["notifications"]
    assert len(elenco) == 1
    assert elenco[0]["severity_source"] == "missing"
    assert "nessun invio" in elenco[0]["content_preview"]

    dettaglio = await api_client.get(f"/api/v1/notifications/{elenco[0]['id']}", headers=headers)
    assert dettaglio.status_code == 200
    assert dettaglio.json()["severity_source"] == "missing"
    # Nessun mittente: e' il segno che l'ha scritta il server.
    assert dettaglio.json()["source_ip"] is None


@pytest.mark.e2e
async def test_filtro_origine_sconosciuta_rifiutato(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await api_client.get(
        "/api/v1/notifications", params={"source": "inventata"}, headers=headers
    )
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_patch_accende_la_sorveglianza_e_conta_da_adesso(
    api_client, two_tenants, owner_token
):
    """Accendere l'attesa su un receiver che riceve da mesi non deve allarmare
    subito: la finestra parte dalla PATCH, non dall'ultimo invio."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers)
    receiver_id = resp.json()["id"]
    assert resp.json()["expected_since"] is None

    # Ultimo invio molto piu' vecchio della finestra che sta per essere accesa.
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == uuid.UUID(receiver_id))
            .values(
                last_notification_at=datetime.now(UTC) - timedelta(days=30),
                missing_alerted_at=datetime.now(UTC) - timedelta(days=29),
            )
        )

    accesa = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json=ATTESA_GIORNALIERA, headers=headers
    )
    assert accesa.status_code == 200
    body = accesa.json()
    assert body["missing_severity"] == "critical"
    assert body["expected_since"] is not None
    poco_fa = datetime.now(UTC) - timedelta(minutes=5)
    assert datetime.fromisoformat(body["expected_since"]) > poco_fa
    # Nessun allarme ereditato e nessun ritardo al primo istante di vita.
    assert body["missing_alerted_at"] is None
    assert body["expected_late"] is False


@pytest.mark.e2e
async def test_riaccendere_un_receiver_fa_ripartire_l_attesa(api_client, two_tenants, owner_token):
    """Il silenzio di un receiver disabilitato e' voluto (l'ingestion gli risponde
    404): riattivandolo la finestra riparte, altrimenti allarmerebbe entro un
    minuto per un job che magari gira alle 3 di notte."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver_id = resp.json()["id"]

    spento = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"status": "disabled"}, headers=headers
    )
    assert spento.status_code == 200

    # Una settimana di stop: in ritardo per qualunque conto.
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == uuid.UUID(receiver_id))
            .values(
                last_notification_at=datetime.now(UTC) - timedelta(days=7),
                expected_since=datetime.now(UTC) - timedelta(days=7),
            )
        )

    riacceso = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"status": "active"}, headers=headers
    )
    assert riacceso.status_code == 200
    body = riacceso.json()
    assert body["status"] == "active"
    assert body["expected_late"] is False
    poco_fa = datetime.now(UTC) - timedelta(minutes=5)
    assert datetime.fromisoformat(body["expected_since"]) > poco_fa
    assert body["missing_alerted_at"] is None


@pytest.mark.e2e
async def test_patch_su_receiver_gia_attivo_non_sposta_la_finestra(
    api_client, two_tenants, owner_token
):
    """Il contrappunto del test precedente: una PATCH qualsiasi su un receiver
    che era gia' attivo non deve azzerare il ritardo in corso, o basterebbe
    rinominare un receiver per far sparire un allarme."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver_id = resp.json()["id"]

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == uuid.UUID(receiver_id))
            .values(
                last_notification_at=datetime.now(UTC) - timedelta(days=7),
                expected_since=datetime.now(UTC) - timedelta(days=7),
            )
        )

    rinominato = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"name": "backup notturno v2"}, headers=headers
    )
    assert rinominato.status_code == 200
    assert rinominato.json()["expected_late"] is True

    # Il form della UI rimanda sempre tutti e cinque i campi dell'attesa, anche
    # quando non li ha toccati: nemmeno quella e' una riaccensione.
    reinviato = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}",
        json={**ATTESA_GIORNALIERA, "expected_cron": None, "expected_timezone": None},
        headers=headers,
    )
    assert reinviato.status_code == 200
    assert reinviato.json()["expected_late"] is True


@pytest.mark.e2e
@pytest.mark.parametrize("cron", ["0 0 30 2 *", "0 0 31 4 *"])
async def test_cron_che_non_scatta_mai_rifiutato(api_client, two_tenants, owner_token, cron):
    """Sintatticamente validi ma senza nessuna data che li soddisfi: accettarli
    vorrebbe dire una sorveglianza che non allarmera' mai, cioe' il contrario di
    quello che l'utente ha chiesto."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(
        api_client,
        headers,
        {"expected_cron": cron, "expected_grace_seconds": 900, "missing_severity": "error"},
    )
    assert resp.status_code == 422
    assert "non scatta mai" in resp.text


@pytest.mark.e2e
async def test_patch_da_cron_a_intervallo_richiede_di_azzerare_il_fuso(
    api_client, two_tenants, owner_token
):
    """Simmetrico di test_patch_da_intervallo_a_cron: expected_timezone appartiene
    alla forma cron, quindi tornare all'intervallo va chiesto in modo esplicito."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(
        api_client,
        headers,
        {
            "expected_cron": "0 3 * * *",
            "expected_timezone": "Europe/Rome",
            "expected_grace_seconds": 900,
            "missing_severity": "error",
        },
    )
    receiver_id = resp.json()["id"]

    mezzo = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}",
        json={"expected_cron": None, "expected_every_seconds": 3600},
        headers=headers,
    )
    assert mezzo.status_code == 422
    assert "expected_timezone" in mezzo.text

    ok = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}",
        json={"expected_cron": None, "expected_timezone": None, "expected_every_seconds": 3600},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json()["expected_every_seconds"] == 3600
    assert ok.json()["expected_cron"] is None
    assert ok.json()["expected_timezone"] is None


@pytest.mark.e2e
async def test_senza_riferimento_la_scadenza_resta_vuota(api_client, two_tenants, owner_token):
    """Politica attiva ma nessun invio e nessun expected_since (riga scritta a
    mano o migrata): non c'e' da cosa misurare, e la dashboard deve dirlo invece
    di inventarsi una data - stessa scelta del job."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, resp = await _gruppo_e_receiver(api_client, headers, ATTESA_GIORNALIERA)
    receiver_id = resp.json()["id"]

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == uuid.UUID(receiver_id))
            .values(expected_since=None, last_notification_at=None)
        )

    detail = await api_client.get(f"/api/v1/receivers/{receiver_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["missing_severity"] == "critical"
    assert body["expected_deadline_at"] is None
    assert body["expected_late"] is False


@pytest.mark.e2e
async def test_cron_malformato_in_colonna_non_rompe_l_elenco(api_client, two_tenants, owner_token):
    """Un cron arrivato in colonna per altre strade (migrazione, SQL a mano) non
    deve far fallire l'elenco di tutti gli altri receiver: resta senza scadenza."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_id, resp = await _gruppo_e_receiver(
        api_client,
        headers,
        {
            "expected_cron": "0 3 * * *",
            "expected_timezone": "Europe/Rome",
            "expected_grace_seconds": 900,
            "missing_severity": "error",
        },
    )
    receiver_id = resp.json()["id"]

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == uuid.UUID(receiver_id))
            .values(expected_timezone="Europa/Roma")
        )

    elenco = await api_client.get(f"/api/v1/groups/{group_id}/receivers", headers=headers)
    assert elenco.status_code == 200
    riga = next(r for r in elenco.json() if r["id"] == receiver_id)
    assert riga["expected_deadline_at"] is None
    assert riga["expected_late"] is False
