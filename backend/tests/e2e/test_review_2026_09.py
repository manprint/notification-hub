"""E2E di regressione per i difetti della review di settembre 2026.

Ogni test fallisce sul codice precedente alla correzione: logout che non
revocava niente, elenco utenti leggibile da tutti, admin che agiva sugli owner,
campi che non si potevano piu' riportare a vuoto/illimitato, consegne troncate
a 100 senza paginazione, bulk-read che ignorava il filtro sullo stato, interi
oltre int4 che diventavano un 500, cron casuali accettati.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.crypto import encrypt_secret
from app.db.session import tenant_session
from app.db.types import DeliveryStatus, Severity
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.notification import Notification
from tests.conftest_factories import create_group, create_receiver

PASSWORD = "correct-horse-battery"  # noqa: S105


async def _headers(api_client, tenant_id: uuid.UUID, owner_token) -> dict:
    return {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}


async def _create_user(api_client, headers, role: str, group_ids: list | None = None) -> dict:
    resp = await api_client.post(
        "/api/v1/users",
        json={
            "email": f"{role}-{uuid.uuid4().hex[:8]}@test.com",
            "password": PASSWORD,
            "role": role,
            "group_ids": [str(g) for g in group_ids or []],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _login(api_client, email: str) -> dict:
    resp = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --- Logout -----------------------------------------------------------------


@pytest.mark.e2e
async def test_logout_col_refresh_token_revoca_la_sua_famiglia(
    api_client, two_tenants, owner_token
):
    """La dashboard mandava `{}`: il filtro `jti == None` non trovava niente e il
    refresh token restava valido per 30 giorni dopo "Esci"."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    user = await _create_user(api_client, headers, "member")

    sessione = await _login(api_client, user["email"])
    altra_sessione = await _login(api_client, user["email"])

    # Una rotazione prima del logout: la famiglia ha ora un token revocato e uno
    # vivo, ed e' quello vivo che il client presenta.
    ruotato = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": sessione["refresh_token"]}
    )
    assert ruotato.status_code == 200
    ruotato_tokens = ruotato.json()

    logout = await api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": ruotato_tokens["refresh_token"]},
        headers=_bearer(ruotato_tokens),
    )
    assert logout.status_code == 204

    dopo = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": ruotato_tokens["refresh_token"]}
    )
    assert dopo.status_code == 401

    # Solo QUESTA sessione: le altre dello stesso utente restano valide.
    altra = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": altra_sessione["refresh_token"]}
    )
    assert altra.status_code == 200


@pytest.mark.e2e
async def test_logout_non_revoca_il_refresh_token_di_un_altro_utente(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    primo = await _create_user(api_client, headers, "member")
    secondo = await _create_user(api_client, headers, "member")
    sessione_primo = await _login(api_client, primo["email"])
    sessione_secondo = await _login(api_client, secondo["email"])

    logout = await api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": sessione_secondo["refresh_token"]},
        headers=_bearer(sessione_primo),
    )
    assert logout.status_code == 204
    ancora_valido = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": sessione_secondo["refresh_token"]}
    )
    assert ancora_valido.status_code == 200


# --- Utenti -----------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("ruolo", ["member", "viewer"])
async def test_elenco_utenti_riservato_ad_admin(api_client, two_tenants, owner_token, ruolo):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    utente = await _create_user(api_client, headers, ruolo)
    sessione = await _login(api_client, utente["email"])

    elenco = await api_client.get("/api/v1/users", headers=_bearer(sessione))
    assert elenco.status_code == 403
    dettaglio = await api_client.get(f"/api/v1/users/{utente['id']}", headers=_bearer(sessione))
    assert dettaglio.status_code == 403


@pytest.mark.e2e
async def test_admin_non_modifica_ne_rimuove_un_owner(api_client, two_tenants, owner_token):
    """Con due owner il vincolo sull'ultimo owner non scattava: un admin poteva
    declassare, disabilitare o rimuovere uno dei due."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    secondo_owner = await _create_user(api_client, headers, "owner")
    admin = await _create_user(api_client, headers, "admin")
    admin_headers = _bearer(await _login(api_client, admin["email"]))

    declassa = await api_client.patch(
        f"/api/v1/users/{secondo_owner['id']}", json={"role": "viewer"}, headers=admin_headers
    )
    assert declassa.status_code == 403
    disabilita = await api_client.patch(
        f"/api/v1/users/{secondo_owner['id']}", json={"status": "disabled"}, headers=admin_headers
    )
    assert disabilita.status_code == 403
    rimuovi = await api_client.delete(f"/api/v1/users/{secondo_owner['id']}", headers=admin_headers)
    assert rimuovi.status_code == 403

    # Un owner invece puo'.
    da_owner = await api_client.patch(
        f"/api/v1/users/{secondo_owner['id']}", json={"role": "admin"}, headers=headers
    )
    assert da_owner.status_code == 200
    assert da_owner.json()["role"] == "admin"


@pytest.mark.e2e
async def test_admin_modifica_ancora_i_member(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    member = await _create_user(api_client, headers, "member")
    admin = await _create_user(api_client, headers, "admin")
    admin_headers = _bearer(await _login(api_client, admin["email"]))

    resp = await api_client.patch(
        f"/api/v1/users/{member['id']}", json={"role": "viewer"}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"


# --- Gruppi e tenant: tornare a vuoto / illimitato ---------------------------


@pytest.mark.e2e
async def test_descrizione_del_gruppo_si_puo_svuotare(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    creato = await api_client.post(
        "/api/v1/groups",
        json={"name": f"g-{uuid.uuid4().hex[:6]}", "description": "da togliere"},
        headers=headers,
    )
    assert creato.status_code == 201
    group_id = creato.json()["id"]

    # Campo assente: invariata.
    rinomina = await api_client.patch(
        f"/api/v1/groups/{group_id}", json={"name": "nuovo nome"}, headers=headers
    )
    assert rinomina.json()["description"] == "da togliere"

    svuota = await api_client.patch(
        f"/api/v1/groups/{group_id}", json={"description": None}, headers=headers
    )
    assert svuota.status_code == 200
    assert svuota.json()["description"] is None

    await api_client.patch(
        f"/api/v1/groups/{group_id}", json={"description": "di nuovo"}, headers=headers
    )
    vuota = await api_client.patch(
        f"/api/v1/groups/{group_id}", json={"description": ""}, headers=headers
    )
    assert vuota.json()["description"] is None


@pytest.mark.e2e
async def test_quote_del_tenant_tornano_illimitate(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)

    imposta = await api_client.patch(
        "/api/v1/tenant",
        json={
            "max_notifications_per_day": 1000,
            "max_storage_bytes": 10_000_000,
            "retention_days": 30,
            "audit_retention_days": 400,
        },
        headers=headers,
    )
    assert imposta.status_code == 200, imposta.text

    # Un campo non inviato resta com'era.
    solo_nome = await api_client.patch("/api/v1/tenant", json={"name": "Acme"}, headers=headers)
    assert solo_nome.json()["max_notifications_per_day"] == 1000

    illimitate = await api_client.patch(
        "/api/v1/tenant",
        json={
            "max_notifications_per_day": None,
            "max_storage_bytes": None,
            "retention_days": None,
            "audit_retention_days": None,
        },
        headers=headers,
    )
    assert illimitate.status_code == 200
    corpo = illimitate.json()
    assert corpo["max_notifications_per_day"] is None
    assert corpo["max_storage_bytes"] is None
    assert corpo["retention_days"] is None
    assert corpo["audit_retention_days"] is None

    # name e max_body_bytes non hanno un "illimitato": null resta ignorato.
    ignorati = await api_client.patch(
        "/api/v1/tenant", json={"name": None, "max_body_bytes": None}, headers=headers
    )
    assert ignorati.status_code == 200
    assert ignorati.json()["name"] == "Acme"


# --- Consegne: paginazione a cursore ------------------------------------------


async def _consegne(tenant_id: uuid.UUID, quante: int) -> set[str]:
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    channel_id = uuid.uuid4()
    ids: set[str] = set()
    async with tenant_session(tenant_id) as session:
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name="Slack #ops",
                type="slack",
                webhook_url=encrypt_secret("https://hooks.slack.com/services/T0/B0/X0"),
                enabled=True,
            )
        )
        await session.flush()
        base = datetime.now(UTC)
        for i in range(quante):
            notification_id = uuid.uuid4()
            session.add(
                Notification(
                    id=notification_id,
                    tenant_id=tenant_id,
                    receiver_id=receiver_id,
                    content=f"n{i}",
                    content_preview=f"n{i}",
                    content_size=2,
                    content_normalized=False,
                    storage_backend="inline",
                    severity=Severity.ERROR,
                    severity_source="receiver_default",
                    status="unread",
                    # Due consegne con lo stesso istante: l'ordine deve restare
                    # totale grazie all'id, senza doppioni fra le pagine.
                    received_at=base - timedelta(seconds=i // 2),
                )
            )
            await session.flush()
            delivery_id = uuid.uuid4()
            session.add(
                Delivery(
                    id=delivery_id,
                    tenant_id=tenant_id,
                    notification_id=notification_id,
                    channel_id=channel_id,
                    status=DeliveryStatus.DEAD,
                    attempts=5,
                    next_attempt_at=base,
                )
            )
            ids.add(str(delivery_id))
        await session.flush()
    return ids


@pytest.mark.e2e
async def test_consegne_paginate_senza_perdite_ne_doppioni(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    attese = await _consegne(tenant_id, 5)

    viste: list[str] = []
    cursor = None
    pagine = 0
    while True:
        params = {"status": "dead", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await api_client.get("/api/v1/deliveries", params=params, headers=headers)
        assert resp.status_code == 200, resp.text
        pagina = resp.json()
        assert len(pagina["deliveries"]) <= 2
        viste.extend(d["id"] for d in pagina["deliveries"])
        pagine += 1
        cursor = pagina["next_cursor"]
        if cursor is None:
            break
        assert pagine < 10

    assert len(viste) == len(set(viste)), "consegne duplicate fra le pagine"
    assert attese <= set(viste)


@pytest.mark.e2e
async def test_cursore_consegne_non_valido_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    resp = await api_client.get(
        "/api/v1/deliveries", params={"cursor": "non-un-cursore"}, headers=headers
    )
    assert resp.status_code == 422


# --- Bulk-read: stesso filtro sullo stato della lista ------------------------


@pytest.mark.e2e
async def test_bulk_read_con_filtro_solo_lette_non_tocca_le_non_lette(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"g-{uuid.uuid4().hex[:6]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    notification_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            Notification(
                id=notification_id,
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                content="x",
                content_preview="x",
                content_size=1,
                content_normalized=False,
                storage_backend="inline",
                severity=Severity.ERROR,
                severity_source="receiver_default",
                status="unread",
                received_at=datetime.now(UTC),
            )
        )

    resp = await api_client.post(
        "/api/v1/notifications/bulk-read",
        json={"receiver_id": str(receiver_id), "status": "read"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["marked_read"] == 0
    async with tenant_session(tenant_id) as session:
        notification = await session.get(Notification, notification_id)
        assert notification.status == "unread"


# --- Limiti int4 e cron ----------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize(
    "patch",
    [
        {"rate_limit_per_min": 2**31},
        # Politiche complete: senza la severity sarebbero 422 per "meta'
        # configurata", e il test non direbbe niente sul limite.
        {"expected_every_seconds": 2**31, "expected_grace_seconds": 0, "missing_severity": "error"},
        {"duration_threshold_seconds": 2**31, "duration_severity": "warning"},
    ],
)
async def test_interi_oltre_int4_sono_422_non_500(api_client, two_tenants, owner_token, patch):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    valido = {k: (2**31 - 1 if v == 2**31 else v) for k, v in patch.items()}
    ok = await api_client.patch(f"/api/v1/receivers/{receiver_id}", json=valido, headers=headers)
    assert ok.status_code == 200, ok.text
    resp = await api_client.patch(f"/api/v1/receivers/{receiver_id}", json=patch, headers=headers)
    assert resp.status_code == 422, resp.text


@pytest.mark.e2e
@pytest.mark.parametrize("cron", ["R * * * *", "0 R * * *", "0 3 r/2 * *"])
async def test_cron_casuale_rifiutato(api_client, two_tenants, owner_token, cron):
    """croniter accetta `R` ma estrae un valore nuovo a ogni istanza: la scadenza
    della sorveglianza cambiava a ogni controllo."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group = await api_client.post(
        "/api/v1/groups", json={"name": f"g-{uuid.uuid4().hex[:6]}"}, headers=headers
    )
    resp = await api_client.post(
        f"/api/v1/groups/{group.json()['id']}/receivers",
        json={
            "name": "job",
            "expected_cron": cron,
            "expected_timezone": "Europe/Rome",
            "expected_grace_seconds": 600,
            "missing_severity": "error",
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
