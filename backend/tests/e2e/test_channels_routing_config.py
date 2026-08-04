"""Canali, binding di gruppo e override per receiver: dove finiscono le notifiche.

E' la superficie di configurazione dell'inoltro, ed era coperta a meta' (61%):
creare un canale era testato, modificarlo, spegnerlo, legarlo a un gruppo,
slegarlo e sovrascriverlo per receiver no. Sono le operazioni che si fanno in
produzione a impianto acceso, e un errore qui non da' errore: smette di arrivare
qualcosa, e nessuno lo nota.
"""

import uuid

import pytest

WEBHOOK = "https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXXXXXXXXXX"
ALTRO_WEBHOOK = "https://hooks.slack.com/services/T111/B111/YYYYYYYYYYYYYYYYYYYY"


async def _headers(api_client, owner_token, tenant_id) -> dict[str, str]:
    token = await owner_token(api_client, tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _canale(api_client, headers, **override) -> dict:
    corpo = {
        "name": f"Slack {uuid.uuid4().hex[:6]}",
        "type": "slack",
        "webhook_url": WEBHOOK,
    }
    corpo.update(override)
    resp = await api_client.post("/api/v1/channels", json=corpo, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _gruppo(api_client, headers) -> str:
    resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Gruppo {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _receiver(api_client, headers, group_id: str) -> dict:
    resp = await api_client.post(
        f"/api/v1/groups/{group_id}/receivers", json={"name": "job"}, headers=headers
    )
    assert resp.status_code == 201
    return resp.json()


# --- canale -----------------------------------------------------------------


@pytest.mark.e2e
async def test_webhook_mai_restituito_in_chiaro_in_nessuna_lettura(
    api_client, two_tenants, owner_token
):
    """Il webhook e' cifrato a riposo (AES-GCM) e non deve uscire da nessuna delle
    tre letture: creazione, dettaglio, elenco."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)

    creato = await _canale(api_client, headers)
    dettaglio = await api_client.get(f"/api/v1/channels/{creato['id']}", headers=headers)
    elenco = await api_client.get("/api/v1/channels", headers=headers)

    for risposta in (creato, dettaglio.json(), elenco.json()):
        testo = str(risposta)
        assert WEBHOOK not in testo
        assert "T000/B000" not in testo
    # Resta un suggerimento per riconoscere quale webhook e': non l'URL.
    assert creato["webhook_hint"]
    assert WEBHOOK not in creato["webhook_hint"]


@pytest.mark.e2e
async def test_host_fuori_allowlist_rifiutato(api_client, two_tenants, owner_token):
    """SSRF: un webhook verso un host arbitrario farebbe fare al server richieste
    dove vuole chi configura il canale."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)

    for url in (
        "https://evil.example.com/hook",
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:9000/",
    ):
        resp = await api_client.post(
            "/api/v1/channels",
            json={"name": "cattivo", "type": "slack", "webhook_url": url},
            headers=headers,
        )
        assert resp.status_code == 422, f"{url} accettato: {resp.text}"


@pytest.mark.e2e
async def test_modifica_canale_ruota_il_webhook_e_lo_spegne(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    canale = await _canale(api_client, headers)

    patch = await api_client.patch(
        f"/api/v1/channels/{canale['id']}",
        json={"name": "Slack #ops rinominato", "webhook_url": ALTRO_WEBHOOK, "enabled": False},
        headers=headers,
    )
    assert patch.status_code == 200
    corpo = patch.json()
    assert corpo["name"] == "Slack #ops rinominato"
    assert corpo["enabled"] is False
    assert ALTRO_WEBHOOK not in str(corpo)
    # Il suggerimento segue il webhook nuovo, altrimenti l'operatore non
    # distinguerebbe piu' quale ha sostituito.
    assert corpo["webhook_hint"] != canale["webhook_hint"]


@pytest.mark.e2e
async def test_canale_di_un_altro_tenant_e_404(api_client, two_tenants, owner_token):
    tenant_a, tenant_b = two_tenants
    headers_a = await _headers(api_client, owner_token, tenant_a)
    headers_b = await _headers(api_client, owner_token, tenant_b)
    canale = await _canale(api_client, headers_a)

    for metodo, kwargs in (
        ("get", {}),
        ("patch", {"json": {"enabled": False}}),
        ("delete", {}),
    ):
        resp = await getattr(api_client, metodo)(
            f"/api/v1/channels/{canale['id']}", headers=headers_b, **kwargs
        )
        assert resp.status_code == 404, f"{metodo} ha risposto {resp.status_code}"


# --- binding di gruppo ------------------------------------------------------


@pytest.mark.e2e
async def test_ciclo_di_vita_del_binding(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    canale = await _canale(api_client, headers)
    group_id = await _gruppo(api_client, headers)

    legato = await api_client.post(
        f"/api/v1/groups/{group_id}/channels",
        json={"channel_id": canale["id"], "min_severity": "error"},
        headers=headers,
    )
    assert legato.status_code == 201
    assert legato.json()["min_severity"] == "error"
    assert legato.json()["enabled"] is True

    elenco = await api_client.get(f"/api/v1/groups/{group_id}/channels", headers=headers)
    assert [b["channel_id"] for b in elenco.json()] == [canale["id"]]

    alzato = await api_client.put(
        f"/api/v1/groups/{group_id}/channels/{canale['id']}",
        json={"min_severity": "critical", "enabled": False},
        headers=headers,
    )
    assert alzato.status_code == 200
    assert alzato.json()["min_severity"] == "critical"
    assert alzato.json()["enabled"] is False

    slegato = await api_client.delete(
        f"/api/v1/groups/{group_id}/channels/{canale['id']}", headers=headers
    )
    assert slegato.status_code == 204
    dopo = await api_client.get(f"/api/v1/groups/{group_id}/channels", headers=headers)
    assert dopo.json() == []


@pytest.mark.e2e
async def test_binding_verso_un_canale_inesistente_e_404(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    group_id = await _gruppo(api_client, headers)

    resp = await api_client.post(
        f"/api/v1/groups/{group_id}/channels",
        json={"channel_id": str(uuid.uuid4()), "min_severity": "error"},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.e2e
async def test_modificare_un_binding_che_non_esiste_e_404(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    canale = await _canale(api_client, headers)
    group_id = await _gruppo(api_client, headers)

    resp = await api_client.put(
        f"/api/v1/groups/{group_id}/channels/{canale['id']}",
        json={"min_severity": "info"},
        headers=headers,
    )
    assert resp.status_code == 404


# --- override per receiver --------------------------------------------------


@pytest.mark.e2e
async def test_ciclo_di_vita_delloverride(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    canale = await _canale(api_client, headers)
    group_id = await _gruppo(api_client, headers)
    receiver = await _receiver(api_client, headers, group_id)

    creato = await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/channels",
        json={"channel_id": canale["id"], "mode": "override", "min_severity": "critical"},
        headers=headers,
    )
    assert creato.status_code == 201
    assert creato.json()["mode"] == "override"
    assert creato.json()["min_severity"] == "critical"

    elenco = await api_client.get(f"/api/v1/receivers/{receiver['id']}/channels", headers=headers)
    assert len(elenco.json()) == 1

    # Da soglia alzata a silenzio totale: `mute` non richiede una soglia.
    mutato = await api_client.put(
        f"/api/v1/receivers/{receiver['id']}/channels/{canale['id']}",
        json={"mode": "mute", "min_severity": None},
        headers=headers,
    )
    assert mutato.status_code == 200
    assert mutato.json()["mode"] == "mute"

    tolto = await api_client.delete(
        f"/api/v1/receivers/{receiver['id']}/channels/{canale['id']}", headers=headers
    )
    assert tolto.status_code == 204
    assert (
        await api_client.get(f"/api/v1/receivers/{receiver['id']}/channels", headers=headers)
    ).json() == []


@pytest.mark.e2e
async def test_override_senza_soglia_rifiutato(api_client, two_tenants, owner_token):
    """`mode=override` senza `min_severity` non vorrebbe dire niente: l'endpoint lo
    rifiuta invece di scrivere una riga che l'inoltro dovrebbe poi interpretare
    (dove c'e' un assert, non un default silenzioso)."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    canale = await _canale(api_client, headers)
    group_id = await _gruppo(api_client, headers)
    receiver = await _receiver(api_client, headers, group_id)

    resp = await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/channels",
        json={"channel_id": canale["id"], "mode": "override"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_salvare_due_volte_lo_stesso_override_e_idempotente(
    api_client, two_tenants, owner_token
):
    """Contratto dell'endpoint, fissato qui: sulla coppia (receiver, canale) il
    secondo salvataggio aggiorna e risponde 200 invece di violare il vincolo di
    unicita' con un 500. La UI salva senza sapere se l'override esiste gia'."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    canale = await _canale(api_client, headers)
    group_id = await _gruppo(api_client, headers)
    receiver = await _receiver(api_client, headers, group_id)

    primo = await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/channels",
        json={"channel_id": canale["id"], "mode": "mute"},
        headers=headers,
    )
    assert primo.status_code == 201

    secondo = await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/channels",
        json={"channel_id": canale["id"], "mode": "override", "min_severity": "warning"},
        headers=headers,
    )
    assert secondo.status_code == 200
    assert secondo.json()["id"] == primo.json()["id"]  # aggiornato, non duplicato
    assert secondo.json()["mode"] == "override"
    assert secondo.json()["min_severity"] == "warning"

    elenco = await api_client.get(f"/api/v1/receivers/{receiver['id']}/channels", headers=headers)
    assert len(elenco.json()) == 1


# --- prova del canale -------------------------------------------------------


@pytest.mark.e2e
async def test_prova_canale_riporta_lesito_senza_far_fallire_la_richiesta(
    api_client, two_tenants, owner_token
):
    """La prova di un canale verso un webhook che non risponde deve tornare 200 con
    `sent: false` e il motivo: un errore HTTP renderebbe indistinguibile "il canale
    non funziona" da "l'endpoint di prova non funziona"."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    canale = await _canale(api_client, headers)

    resp = await api_client.post(f"/api/v1/channels/{canale['id']}/test", headers=headers)
    assert resp.status_code == 200
    corpo = resp.json()
    assert set(corpo) == {"sent", "detail"}
    assert corpo["sent"] is False  # hooks.slack.com rifiuta un webhook inventato
    assert corpo["detail"]


@pytest.mark.e2e
async def test_eliminare_un_canale_legato_a_un_gruppo(api_client, two_tenants, owner_token):
    """Il caso che in produzione capita per sbaglio: si cancella un canale ancora
    legato. Qualunque sia la scelta (cascade o 409), non deve essere un 500 e lo
    stato dopo deve essere coerente."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    canale = await _canale(api_client, headers)
    group_id = await _gruppo(api_client, headers)
    await api_client.post(
        f"/api/v1/groups/{group_id}/channels",
        json={"channel_id": canale["id"], "min_severity": "error"},
        headers=headers,
    )

    resp = await api_client.delete(f"/api/v1/channels/{canale['id']}", headers=headers)
    assert resp.status_code in (204, 409), resp.text

    binding = await api_client.get(f"/api/v1/groups/{group_id}/channels", headers=headers)
    if resp.status_code == 204:
        # Cancellato: non deve restare un binding che punta al nulla.
        assert binding.json() == []
    else:
        assert [b["channel_id"] for b in binding.json()] == [canale["id"]]


@pytest.mark.e2e
async def test_viewer_non_configura_linoltro(api_client, two_tenants, make_user):
    """Il viewer vede le diagnostiche ma non deve poter spostare le soglie: da
    quelle dipende chi viene svegliato di notte."""
    from app.core.security import hash_password

    tenant_id, _ = two_tenants
    email = f"viewer-{uuid.uuid4().hex[:8]}@acme-notifyhub.com"
    password = "viewer-password-123"
    await make_user(tenant_id, email, hash_password(password))
    from sqlalchemy import update

    from app.db.session import tenant_session
    from app.db.types import UserRole
    from app.models.user import User

    async with tenant_session(tenant_id) as session:
        await session.execute(update(User).where(User.email == email).values(role=UserRole.VIEWER))

    login = await api_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    creazione = await api_client.post(
        "/api/v1/channels",
        json={"name": "da viewer", "type": "slack", "webhook_url": WEBHOOK},
        headers=headers,
    )
    assert creazione.status_code == 403
