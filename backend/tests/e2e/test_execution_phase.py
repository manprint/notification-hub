"""Fase dell'esecuzione (`X-Phase`): il ping di avvio e cosa cambia.

Senza il ping di avvio, "il cron non e' partito" e "il job e' partito e non ha mai
concluso" arrivano al server come lo stesso silenzio. Questi test coprono la
distinzione: il ping aggiorna un istante diverso, si vede in elenco e non viene
mai confuso con una conclusione.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.db.session import tenant_session
from app.db.types import NotificationPhase
from app.models.receiver import Receiver


async def _receiver_row(tenant_id: uuid.UUID, receiver_id: uuid.UUID) -> Receiver:
    async with tenant_session(tenant_id) as session:
        result = await session.execute(select(Receiver).where(Receiver.id == receiver_id))
        return result.scalar_one()


async def _gruppo_e_receiver(api_client, headers):
    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Fasi {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    group_id = group_resp.json()["id"]
    receiver_resp = await api_client.post(
        f"/api/v1/groups/{group_id}/receivers",
        json={
            "name": "backup notturno",
            "expected_every_seconds": 86400,
            "expected_grace_seconds": 1800,
            "missing_severity": "critical",
        },
        headers=headers,
    )
    assert receiver_resp.status_code == 201
    return receiver_resp.json()


@pytest.mark.e2e
async def test_ping_di_avvio_non_conta_come_conclusione(api_client, two_tenants, owner_token):
    """Il punto dell'intera feature: se un avvio contasse come conclusione, la
    sorveglianza tacerebbe proprio quando il job muore dopo essere partito."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="[notifyhub] avvio",
        headers={"X-Phase": "start", "X-Severity": "debug"},
    )
    assert resp.status_code == 201

    row = await _receiver_row(tenant_id, uuid.UUID(receiver["id"]))
    assert row.last_start_at is not None
    assert row.last_notification_at is None


@pytest.mark.e2e
async def test_conclusione_aggiorna_solo_la_conclusione(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)

    await api_client.post(
        f"/ingest/{receiver['slug']}", content="avvio", headers={"X-Phase": "start"}
    )
    prima = await _receiver_row(tenant_id, uuid.UUID(receiver["id"]))

    await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="esito",
        headers={"X-Phase": "end", "X-Exit-Code": "0"},
    )
    dopo = await _receiver_row(tenant_id, uuid.UUID(receiver["id"]))

    assert dopo.last_notification_at is not None
    assert dopo.last_start_at == prima.last_start_at


@pytest.mark.e2e
async def test_senza_header_la_notifica_chiude_come_prima(api_client, two_tenants, owner_token):
    """Nessuna regressione per chi non dichiara la fase: resta una conclusione,
    con `phase` NULL."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)

    await api_client.post(f"/ingest/{receiver['slug']}", content="curl a mano")

    row = await _receiver_row(tenant_id, uuid.UUID(receiver["id"]))
    assert row.last_notification_at is not None
    assert row.last_start_at is None

    lista = await api_client.get(
        "/api/v1/notifications", params={"receiver_id": receiver["id"]}, headers=headers
    )
    assert lista.json()["notifications"][0]["phase"] is None


@pytest.mark.e2e
@pytest.mark.parametrize("valore", ["boh", "", "START ", "avvio", "1"])
async def test_header_fase_non_valido_ignorato(api_client, two_tenants, owner_token, valore):
    """Invariante I-7: un'intestazione scritta male non fa mai fallire
    l'ingestion. `START ` con lo spazio invece deve funzionare, viene ripulita."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}", content="corpo", headers={"X-Phase": valore}
    )
    assert resp.status_code == 201

    row = await _receiver_row(tenant_id, uuid.UUID(receiver["id"]))
    if valore.strip().lower() == "start":
        assert row.last_start_at is not None
    else:
        assert row.last_start_at is None
        assert row.last_notification_at is not None


@pytest.mark.e2e
async def test_fase_visibile_in_elenco_e_dettaglio(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)

    await api_client.post(
        f"/ingest/{receiver['slug']}", content="avvio", headers={"X-Phase": "start"}
    )
    await api_client.post(
        f"/ingest/{receiver['slug']}", content="esito", headers={"X-Phase": "end"}
    )

    lista = await api_client.get(
        "/api/v1/notifications", params={"receiver_id": receiver["id"]}, headers=headers
    )
    fasi = [n["phase"] for n in lista.json()["notifications"]]
    assert set(fasi) == {"start", "end"}

    avvio_id = next(n["id"] for n in lista.json()["notifications"] if n["phase"] == "start")
    dettaglio = await api_client.get(f"/api/v1/notifications/{avvio_id}", headers=headers)
    assert dettaglio.json()["phase"] == "start"


@pytest.mark.e2e
async def test_ultimo_avvio_esposto_sul_receiver(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)
    assert receiver["last_start_at"] is None

    await api_client.post(
        f"/ingest/{receiver['slug']}", content="avvio", headers={"X-Phase": "start"}
    )

    detail = await api_client.get(f"/api/v1/receivers/{receiver['id']}", headers=headers)
    assert detail.json()["last_start_at"] is not None
    # Un avvio non sposta la scadenza dell'attesa: quella la muove la conclusione.
    assert detail.json()["last_notification_at"] is None


@pytest.mark.e2e
async def test_avvio_senza_conclusione_finisce_nella_notifica_di_assenza(
    api_client, two_tenants, owner_token
):
    """La resa pratica: l'allarme dice "partito e interrotto" invece di lasciare
    l'operatore a indovinare fra macchina spenta e job morto."""
    from app.tasks.maintenance import check_expected_schedules

    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)
    receiver_id = uuid.UUID(receiver["id"])

    now = datetime.now(UTC)
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(
                last_notification_at=now - timedelta(days=3),
                last_start_at=now - timedelta(days=2),
                # La sorveglianza conta dal piu' recente fra l'ultimo invio e
                # `expected_since` (services/surveillance.reference_instant):
                # per simulare un receiver muto da tre giorni vanno indietro
                # entrambi, altrimenti la politica risulta accesa un istante fa.
                expected_since=now - timedelta(days=10),
            )
        )

    check_expected_schedules()

    lista = await api_client.get(
        "/api/v1/notifications",
        params={"receiver_id": receiver["id"], "source": "missing"},
        headers=headers,
    )
    assenze = lista.json()["notifications"]
    assert len(assenze) == 1
    dettaglio = await api_client.get(f"/api/v1/notifications/{assenze[0]['id']}", headers=headers)
    contenuto = dettaglio.json()["content"]
    assert "E' partito e si e' interrotto" in contenuto
    # La notifica di assenza non dichiara una fase: non l'ha inviata nessuno.
    assert dettaglio.json()["phase"] is None


@pytest.mark.e2e
async def test_senza_ping_di_avvio_lassenza_dichiara_di_non_sapere(
    api_client, two_tenants, owner_token
):
    from app.tasks.maintenance import check_expected_schedules

    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == uuid.UUID(receiver["id"]))
            .values(
                last_notification_at=datetime.now(UTC) - timedelta(days=3),
                expected_since=datetime.now(UTC) - timedelta(days=10),
            )
        )

    check_expected_schedules()

    lista = await api_client.get(
        "/api/v1/notifications",
        params={"receiver_id": receiver["id"], "source": "missing"},
        headers=headers,
    )
    dettaglio = await api_client.get(
        f"/api/v1/notifications/{lista.json()['notifications'][0]['id']}", headers=headers
    )
    assert "--ping-start" in dettaglio.json()["content"]


@pytest.mark.e2e
async def test_ping_di_avvio_rispetta_la_severity_esplicita(api_client, two_tenants, owner_token):
    """Il wrapper manda l'avvio con severity debug: non deve poter finire sui
    canali per colpa di una regola sul contenuto."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)

    await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/severity-rules",
        json={"pattern": "avvio", "severity": "critical"},
        headers=headers,
    )

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="[notifyhub] avvio del job",
        headers={"X-Phase": "start", "X-Severity": "debug"},
    )
    assert resp.status_code == 201
    assert resp.json()["severity"] == "debug"
    assert resp.json()["severity_source"] == "explicit"


@pytest.mark.e2e
async def test_enum_della_fase_allineato_al_database(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    receiver = await _gruppo_e_receiver(api_client, headers)

    for fase in NotificationPhase:
        resp = await api_client.post(
            f"/ingest/{receiver['slug']}", content="x", headers={"X-Phase": fase.value}
        )
        assert resp.status_code == 201
