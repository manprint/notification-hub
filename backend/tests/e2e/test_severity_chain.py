"""E2E della catena di severity: scansione del contenuto intero, politica
sull'exit code, unicita e riordino delle priorita, replay sulle notifiche gia
arrivate."""

import uuid

import pytest

from tests.conftest_factories import create_group, create_receiver

PASSWORD = "correct-horse-battery"  # noqa: S105


async def _headers(api_client, tenant_id, owner_token) -> dict:
    return {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}


async def _make_receiver(api_client, headers, tenant_id, **overrides) -> dict:
    group_id = await create_group(tenant_id, f"g-{uuid.uuid4().hex[:6]}")
    body = {"name": f"r-{uuid.uuid4().hex[:6]}", "default_severity": "info", **overrides}
    resp = await api_client.post(f"/api/v1/groups/{group_id}/receivers", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_rule(api_client, headers, receiver_id, pattern, severity, priority=None) -> dict:
    body = {"pattern": pattern, "severity": severity, "case_insensitive": True, "enabled": True}
    if priority is not None:
        body["priority"] = priority
    resp = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/severity-rules", json=body, headers=headers
    )
    return resp.status_code, resp.json()


# --- scansione del contenuto intero ---------------------------------------


@pytest.mark.e2e
async def test_regola_scatta_oltre_gli_8192_caratteri(api_client, two_tenants, owner_token):
    """Il vecchio motore campionava i primi 8192 caratteri: un errore in fondo a
    un log lungo non faceva scattare nessuna regola."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    status, _ = await _add_rule(api_client, headers, receiver["id"], "CHECKSUM NON VALIDO", "error")
    assert status == 201

    riempimento = "riga di log del tutto innocua\n" * 2000  # ~60 KB
    corpo = riempimento + "CHECKSUM NON VALIDO alla fine del log"
    assert corpo.index("CHECKSUM") > 8192

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}", content=corpo, headers={"Content-Type": "text/plain"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["severity"] == "error"
    assert resp.json()["severity_source"] == "rule"


@pytest.mark.e2e
async def test_contenuto_grande_va_su_thread_e_resta_corretto(api_client, two_tenants, owner_token):
    """Sopra la soglia la scansione viene spostata su un thread: il risultato
    deve essere identico a quello sincrono."""
    from app.services.severity import SCAN_THREAD_THRESHOLD_CHARS

    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    await _add_rule(api_client, headers, receiver["id"], "SEGNALE FINALE", "critical")

    corpo = ("x" * 79 + "\n") * (SCAN_THREAD_THRESHOLD_CHARS // 80 + 100) + "SEGNALE FINALE"
    assert len(corpo) > SCAN_THREAD_THRESHOLD_CHARS

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}", content=corpo, headers={"Content-Type": "text/plain"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["severity"] == "critical"
    assert resp.json()["severity_source"] == "rule"


# --- politica sull'exit code ----------------------------------------------


@pytest.mark.e2e
async def test_exit_code_diverso_da_zero_usa_la_politica_del_receiver(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    await _add_rule(api_client, headers, receiver["id"], "tutto bene", "debug")

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="tutto bene, ma il comando e' fallito",
        headers={"Content-Type": "text/plain", "X-Exit-Code": "3"},
    )
    assert resp.status_code == 201, resp.text
    # critical e' il default della colonna: batte la regola che avrebbe dato debug
    assert resp.json()["severity"] == "critical"
    assert resp.json()["severity_source"] == "exit_code"


@pytest.mark.e2e
async def test_exit_code_zero_lascia_decidere_le_regole(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    await _add_rule(api_client, headers, receiver["id"], "attenzione", "warning")

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="attenzione: spazio quasi esaurito",
        headers={"Content-Type": "text/plain", "X-Exit-Code": "0"},
    )
    assert resp.json()["severity"] == "warning"
    assert resp.json()["severity_source"] == "rule"


@pytest.mark.e2e
async def test_politica_exit_code_disattivabile(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    patched = await api_client.patch(
        f"/api/v1/receivers/{receiver['id']}", json={"exit_code_severity": None}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["exit_code_severity"] is None

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="fallito ma non ci interessa",
        headers={"Content-Type": "text/plain", "X-Exit-Code": "9"},
    )
    assert resp.json()["severity"] == "info"
    assert resp.json()["severity_source"] == "receiver_default"


@pytest.mark.e2e
async def test_severity_esplicita_batte_exit_code(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="fallito, ma lo classifico io",
        headers={"Content-Type": "text/plain", "X-Exit-Code": "1", "X-Severity": "warning"},
    )
    assert resp.json()["severity"] == "warning"
    assert resp.json()["severity_source"] == "explicit"


@pytest.mark.e2e
async def test_exit_code_non_numerico_ignorato(api_client, two_tenants, owner_token):
    """Un'intestazione scritta male non deve mai far fallire l'ingestion."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="messaggio",
        headers={"Content-Type": "text/plain", "X-Exit-Code": "boh"},
    )
    assert resp.status_code == 201
    assert resp.json()["severity_source"] == "receiver_default"


# --- priorita --------------------------------------------------------------


@pytest.mark.e2e
async def test_priorita_duplicata_rifiutata(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    first, _ = await _add_rule(api_client, headers, receiver["id"], "alfa", "error", priority=10)
    assert first == 201
    second, body = await _add_rule(api_client, headers, receiver["id"], "beta", "info", priority=10)
    assert second == 409
    assert "10" in body["detail"]


@pytest.mark.e2e
async def test_priorita_omessa_accodata_in_fondo(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    _, first = await _add_rule(api_client, headers, receiver["id"], "alfa", "error")
    _, second = await _add_rule(api_client, headers, receiver["id"], "beta", "info")
    assert [first["priority"], second["priority"]] == [10, 20]


@pytest.mark.e2e
async def test_riordino_cambia_la_regola_vincente(api_client, two_tenants, owner_token):
    """Due regole che matchano lo stesso testo: vince quella con priorita piu
    bassa. Il riordino inverte l'esito senza toccare i pattern."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    _, prima = await _add_rule(api_client, headers, receiver["id"], "ERRORE", "error")
    _, seconda = await _add_rule(api_client, headers, receiver["id"], "attenzione", "warning")

    testo = "ERRORE recuperabile, attenzione"
    resp = await api_client.post(
        f"/ingest/{receiver['slug']}", content=testo, headers={"Content-Type": "text/plain"}
    )
    assert resp.json()["severity"] == "error"

    reordered = await api_client.put(
        f"/api/v1/receivers/{receiver['id']}/severity-rules/order",
        json={"rule_ids": [seconda["id"], prima["id"]]},
        headers=headers,
    )
    assert reordered.status_code == 200, reordered.text
    assert [r["priority"] for r in reordered.json()] == [10, 20]

    resp = await api_client.post(
        f"/ingest/{receiver['slug']}", content=testo, headers={"Content-Type": "text/plain"}
    )
    assert resp.json()["severity"] == "warning"


@pytest.mark.e2e
async def test_riordino_richiede_elenco_completo(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    _, prima = await _add_rule(api_client, headers, receiver["id"], "alfa", "error")
    await _add_rule(api_client, headers, receiver["id"], "beta", "info")

    resp = await api_client.put(
        f"/api/v1/receivers/{receiver['id']}/severity-rules/order",
        json={"rule_ids": [prima["id"]]},
        headers=headers,
    )
    assert resp.status_code == 422


# --- replay sulle notifiche reali -----------------------------------------


@pytest.mark.e2e
async def test_replay_mostra_cosa_cambierebbe(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    # Nessuna regola: la notifica nasce con la severity di default.
    resp = await api_client.post(
        f"/ingest/{receiver['slug']}",
        content="ERRORE: disco pieno",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.json()["severity"] == "info"

    # Regola aggiunta dopo: il replay deve segnalare la differenza.
    await _add_rule(api_client, headers, receiver["id"], "ERRORE", "error")

    replay = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/severity-rules/replay", headers=headers
    )
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["changed_count"] == 1
    item = body["items"][0]
    assert item["stored_severity"] == "info"
    assert item["replayed_severity"] == "error"
    assert item["replayed_source"] == "rule"
    assert item["matched_pattern"] == "ERRORE"
    assert item["changed"] is True


@pytest.mark.e2e
async def test_replay_senza_notifiche(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    replay = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/severity-rules/replay", headers=headers
    )
    assert replay.status_code == 200
    assert replay.json() == {"items": [], "changed_count": 0}


@pytest.mark.e2e
async def test_replay_negato_fuori_dai_propri_gruppi(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_a = await create_group(tenant_id, f"a-{uuid.uuid4().hex[:6]}")
    group_b = await create_group(tenant_id, f"b-{uuid.uuid4().hex[:6]}")
    receiver_b = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_b)

    email = f"m-{uuid.uuid4().hex[:8]}@test.com"
    created = await api_client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": PASSWORD,
            "role": "member",
            "group_ids": [str(group_a)],
        },
        headers=headers,
    )
    assert created.status_code == 201
    login = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await api_client.get(
        f"/api/v1/receivers/{receiver_b}/severity-rules/replay", headers=member_headers
    )
    assert resp.status_code == 403
