"""Regressioni trovate rileggendo il lavoro della sessione.

Ogni test qui nasce da un difetto reale, non da un'ipotesi: la riga di commento
dice cosa succedeva prima della correzione.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.db.session import tenant_session
from app.db.types import Severity, SeveritySource
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.models.tenant import Tenant

SORVEGLIATO = {
    "expected_every_seconds": 86400,
    "expected_grace_seconds": 1800,
    "missing_severity": "critical",
}


async def _receiver(api_client, headers, payload: dict | None = None) -> dict:
    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Review {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    group_id = group_resp.json()["id"]
    body = {"name": f"job-{uuid.uuid4().hex[:6]}"}
    body.update(payload or {})
    resp = await api_client.post(f"/api/v1/groups/{group_id}/receivers", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _scrivi_in_colonna(tenant_id: uuid.UUID, receiver_id: str, **valori) -> None:
    """Scrive direttamente in colonna, saltando la validazione dell'API: e' la
    strada da cui arrivano i dati che l'API non ha mai visto (ripristino di un
    backup scritto da un'altra versione, correzione a mano, un fuso che l'immagine
    non conosce piu' dopo un aggiornamento di tzdata)."""
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver).where(Receiver.id == uuid.UUID(receiver_id)).values(**valori)
        )


# --- attesa non calcolabile -------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("cron", "timezone"),
    [
        ("non un cron", "UTC"),  # espressione illeggibile
        ("0 3 * * *", "Mars/Olympus"),  # fuso che non esiste
    ],
)
async def test_attesa_non_calcolabile_non_rompe_il_dettaglio(
    api_client, two_tenants, owner_token, cron, timezone
):
    """Prima: croniter/zoneinfo alzavano un'eccezione dentro `_receiver_out` e il
    dettaglio del receiver rispondeva 500."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    receiver = await _receiver(api_client, headers, SORVEGLIATO)
    await _scrivi_in_colonna(
        tenant_id,
        receiver["id"],
        expected_every_seconds=None,
        expected_cron=cron,
        expected_timezone=timezone,
    )

    detail = await api_client.get(f"/api/v1/receivers/{receiver['id']}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    # La politica si vede ancora (va corretta), ma senza scadenza inventata.
    assert body["expected_cron"] == cron
    assert body["expected_deadline_at"] is None
    assert body["expected_late"] is False


@pytest.mark.e2e
async def test_un_receiver_rotto_non_rompe_lelenco(api_client, two_tenants, owner_token):
    """Prima: un solo receiver malformato faceva rispondere 500 a
    `GET /api/v1/receivers`, cioe' rendeva inutilizzabile ogni elenco della
    dashboard, compresi i selettori dei canali."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    rotto = await _receiver(api_client, headers, SORVEGLIATO)
    sano = await _receiver(api_client, headers, SORVEGLIATO)
    await _scrivi_in_colonna(
        tenant_id,
        rotto["id"],
        expected_every_seconds=None,
        expected_cron="0 3 * *",
        expected_timezone="UTC",
    )

    elenco = await api_client.get("/api/v1/receivers", headers=headers)
    assert elenco.status_code == 200
    per_id = {r["id"]: r for r in elenco.json()}
    assert per_id[rotto["id"]]["expected_deadline_at"] is None
    # Il receiver sano continua a esporre la sua scadenza.
    assert per_id[sano["id"]]["expected_deadline_at"] is not None


@pytest.mark.e2e
async def test_il_job_salta_il_receiver_rotto_e_avvisa_sugli_altri(
    api_client, two_tenants, owner_token
):
    """Prima: `alert_deadline` alzava un'eccezione dentro il ciclo del job, che
    moriva a ogni giro. Effetto reale: la sorveglianza spenta per TUTTI i tenant,
    in silenzio, per colpa di una riga sola."""
    from app.tasks.maintenance import check_expected_schedules

    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    rotto = await _receiver(api_client, headers, SORVEGLIATO)
    sano = await _receiver(api_client, headers, SORVEGLIATO)
    scaduto = datetime.now(UTC) - timedelta(days=3)
    # `expected_since` indietro insieme all'ultimo invio: l'attesa si conta dal
    # piu' recente dei due (services/surveillance.reference_instant).
    acceso = datetime.now(UTC) - timedelta(days=10)
    await _scrivi_in_colonna(
        tenant_id,
        rotto["id"],
        expected_every_seconds=None,
        expected_cron="99 99 * * *",
        expected_timezone="UTC",
        last_notification_at=scaduto,
        expected_since=acceso,
    )
    await _scrivi_in_colonna(
        tenant_id, sano["id"], last_notification_at=scaduto, expected_since=acceso
    )

    check_expected_schedules()

    async def _assenze(receiver_id: str) -> list[Notification]:
        async with tenant_session(tenant_id) as session:
            result = await session.execute(
                select(Notification).where(
                    Notification.receiver_id == uuid.UUID(receiver_id),
                    Notification.severity_source == SeveritySource.MISSING,
                )
            )
            return list(result.scalars().all())

    assert len(await _assenze(sano["id"])) == 1
    assert await _assenze(rotto["id"]) == []


# --- replay -----------------------------------------------------------------


@pytest.mark.e2e
async def test_replay_ignora_le_notifiche_scritte_dal_server(api_client, two_tenants, owner_token):
    """Prima: il replay rivalutava anche assenze, riprese e ping di avvio. Su un
    receiver sorvegliato di una macchina spenta erano la maggioranza delle ultime
    notifiche, e la risposta "cosa cambierebbe" non mostrava piu' i messaggi veri."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    receiver = await _receiver(api_client, headers, SORVEGLIATO)
    receiver_id = uuid.UUID(receiver["id"])

    # Un messaggio vero, un ping di avvio, e le due sintetiche come le scrive il job.
    await api_client.post(f"/ingest/{receiver['slug']}", content="Backup FALLITO")
    await api_client.post(
        f"/ingest/{receiver['slug']}", content="[notifyhub] avvio", headers={"X-Phase": "start"}
    )
    async with tenant_session(tenant_id) as session:
        for source, severity, testo in (
            (SeveritySource.MISSING, Severity.CRITICAL, "[notifyhub] nessun invio da job"),
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

    replay = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/severity-rules/replay", headers=headers
    )
    assert replay.status_code == 200
    anteprime = [item["content_preview"] for item in replay.json()["items"]]
    assert anteprime == ["Backup FALLITO"]


@pytest.mark.e2e
async def test_replay_tiene_le_notifiche_senza_fase_dichiarata(
    api_client, two_tenants, owner_token
):
    """Il filtro esclude i ping di avvio, non le notifiche con `phase` NULL: quelle
    sono tutto lo storico e ogni invio fatto a mano, e devono restare nel replay
    (confronto `IS DISTINCT FROM`, non `!=`, che con NULL le escluderebbe tutte)."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    receiver = await _receiver(api_client, headers)
    await api_client.post(f"/ingest/{receiver['slug']}", content="senza fase dichiarata")
    await api_client.post(
        f"/ingest/{receiver['slug']}", content="conclusione", headers={"X-Phase": "end"}
    )

    replay = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/severity-rules/replay", headers=headers
    )
    anteprime = {item["content_preview"] for item in replay.json()["items"]}
    assert anteprime == {"senza fase dichiarata", "conclusione"}


# --- scrittura ---------------------------------------------------------------


@pytest.mark.e2e
async def test_cron_e_fuso_normalizzati_in_scrittura(api_client, two_tenants, owner_token):
    """Prima: l'espressione veniva validata sulla forma ripulita ma salvata grezza,
    quindi in dashboard compariva con la spaziatura sbagliata."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    receiver = await _receiver(
        api_client,
        headers,
        {
            "expected_cron": "  0   3  *  *  1-5 ",
            "expected_timezone": " Europe/Rome ",
            "expected_grace_seconds": 900,
            "missing_severity": "error",
        },
    )
    assert receiver["expected_cron"] == "0 3 * * 1-5"
    assert receiver["expected_timezone"] == "Europe/Rome"
    assert receiver["expected_deadline_at"] is not None


# --- interazioni fra pezzi diversi ------------------------------------------


@pytest.mark.e2e
async def test_invio_ripetuto_non_falsa_il_battito(api_client, two_tenants, owner_token):
    """Un reinvio idempotente (`X-Request-Id` ripetuto) risponde 200 senza
    scrivere: non deve nemmeno spostare l'ultima conclusione, altrimenti un cron
    che ritenta lo stesso messaggio terrebbe viva la sorveglianza di un job che
    non gira piu'."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    receiver = await _receiver(api_client, headers, SORVEGLIATO)
    request_id = f"review-{uuid.uuid4().hex[:8]}"

    primo = await api_client.post(
        f"/ingest/{receiver['slug']}", content="esito", headers={"X-Request-Id": request_id}
    )
    assert primo.status_code == 201

    async def _battito() -> datetime | None:
        async with tenant_session(tenant_id) as session:
            result = await session.execute(
                select(Receiver.last_notification_at).where(
                    Receiver.id == uuid.UUID(receiver["id"])
                )
            )
            return result.scalar_one()

    dopo_il_primo = await _battito()
    assert dopo_il_primo is not None

    ripetuto = await api_client.post(
        f"/ingest/{receiver['slug']}", content="esito", headers={"X-Request-Id": request_id}
    )
    assert ripetuto.status_code == 200  # replay idempotente
    assert await _battito() == dopo_il_primo


@pytest.mark.e2e
async def test_lallarme_passa_anche_a_quota_esaurita(api_client, two_tenants, owner_token):
    """Scelta consapevole, fissata qui: la quota giornaliera del tenant blocca
    l'ingestion (429) ma non le notifiche della sorveglianza. Un allarme "il job
    non gira piu'" soppresso da una quota sarebbe il silenzio proprio nel momento
    in cui serve parlare."""
    from app.tasks.maintenance import check_expected_schedules

    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    receiver = await _receiver(api_client, headers, SORVEGLIATO)
    await _scrivi_in_colonna(
        tenant_id,
        receiver["id"],
        last_notification_at=datetime.now(UTC) - timedelta(days=3),
        expected_since=datetime.now(UTC) - timedelta(days=10),
    )

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Tenant).where(Tenant.id == tenant_id).values(max_notifications_per_day=0)
        )
    try:
        # Quota esaurita: l'ingestion viene rifiutata...
        rifiutata = await api_client.post(f"/ingest/{receiver['slug']}", content="troppo")
        assert rifiutata.status_code == 429

        # ...e l'allarme viene scritto comunque.
        check_expected_schedules()
        async with tenant_session(tenant_id) as session:
            result = await session.execute(
                select(Notification).where(
                    Notification.receiver_id == uuid.UUID(receiver["id"]),
                    Notification.severity_source == SeveritySource.MISSING,
                )
            )
            assert len(list(result.scalars().all())) == 1
    finally:
        async with tenant_session(tenant_id) as session:
            await session.execute(
                update(Tenant).where(Tenant.id == tenant_id).values(max_notifications_per_day=None)
            )
