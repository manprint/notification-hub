"""E2E dei preset di regole: installazione del catalogo, modifica, applicazione
a piu receiver, precedenza fra regole proprie e regole di preset."""

import uuid

import pytest

from tests.conftest_factories import create_group

PASSWORD = "correct-horse-battery"  # noqa: S105


async def _headers(api_client, tenant_id, owner_token) -> dict:
    return {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}


async def _make_receiver(api_client, headers, tenant_id, **overrides) -> dict:
    group_id = await create_group(tenant_id, f"g-{uuid.uuid4().hex[:6]}")
    body = {
        "name": f"r-{uuid.uuid4().hex[:6]}",
        "default_severity": "info",
        # L'exit code non deve interferire: questi test parlano di regole.
        "exit_code_severity": None,
        **overrides,
    }
    resp = await api_client.post(f"/api/v1/groups/{group_id}/receivers", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _new_preset(api_client, headers, name: str, rules: list[dict]) -> dict:
    resp = await api_client.post(
        "/api/v1/severity-presets",
        json={"name": name, "description": "creato dai test"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    preset = resp.json()
    for rule in rules:
        rule_resp = await api_client.post(
            f"/api/v1/severity-presets/{preset['id']}/rules", json=rule, headers=headers
        )
        assert rule_resp.status_code == 201, rule_resp.text
    return preset


async def _apply(api_client, headers, receiver_id: str, preset_ids: list[str]):
    return await api_client.put(
        f"/api/v1/receivers/{receiver_id}/presets",
        json={"preset_ids": preset_ids},
        headers=headers,
    )


async def _ingest(api_client, slug: str, body: str):
    return await api_client.post(
        f"/ingest/{slug}", content=body, headers={"Content-Type": "text/plain"}
    )


# --- catalogo predefinito --------------------------------------------------


@pytest.mark.e2e
async def test_sync_installa_il_catalogo_ed_e_ripetibile(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)

    prima = await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)
    assert prima.status_code == 200, prima.text
    installati = set(prima.json()["installed"])
    assert {"bash-generic", "postgres", "mongodb", "tar", "rclone"} <= installati

    # Seconda esecuzione: nessuna copia doppia, nessun errore.
    seconda = await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)
    assert seconda.status_code == 200
    assert seconda.json()["installed"] == []
    assert set(seconda.json()["already_present"]) >= installati

    elenco = await api_client.get("/api/v1/severity-presets", headers=headers)
    chiavi = [p["builtin_key"] for p in elenco.json()]
    assert len(chiavi) == len(set(chiavi))
    bash = next(p for p in elenco.json() if p["builtin_key"] == "bash-generic")
    assert bash["rules_count"] > 0
    assert bash["receivers_count"] == 0


@pytest.mark.e2e
async def test_catalogo_dice_cosa_e_gia_installato(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)

    prima = await api_client.get("/api/v1/severity-presets/catalog", headers=headers)
    assert prima.status_code == 200
    assert all(voce["installed"] is False for voce in prima.json())

    await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)

    dopo = await api_client.get("/api/v1/severity-presets/catalog", headers=headers)
    assert all(voce["installed"] is True for voce in dopo.json())
    assert all(voce["rules_count"] > 0 for voce in dopo.json())


@pytest.mark.e2e
async def test_preset_predefinito_riconosce_un_errore_bash(api_client, two_tenants, owner_token):
    """Il caso d'uso vero: si applica bash-generic e un output di shell tipico
    diventa error senza scrivere nessuna regola a mano."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)

    elenco = await api_client.get("/api/v1/severity-presets", headers=headers)
    bash = next(p for p in elenco.json() if p["builtin_key"] == "bash-generic")

    receiver = await _make_receiver(api_client, headers, tenant_id)
    assert (await _apply(api_client, headers, receiver["id"], [bash["id"]])).status_code == 200

    resp = await _ingest(api_client, receiver["slug"], "/opt/backup.sh: line 3: Permission denied")
    assert resp.status_code == 201, resp.text
    assert resp.json()["severity"] == "error"
    assert resp.json()["severity_source"] == "preset_rule"

    innocuo = await _ingest(api_client, receiver["slug"], "backup completato, 42 file copiati")
    assert innocuo.json()["severity"] == "info"
    assert innocuo.json()["severity_source"] == "receiver_default"


@pytest.mark.e2e
async def test_ripristino_riporta_il_preset_al_catalogo(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)
    elenco = await api_client.get("/api/v1/severity-presets", headers=headers)
    tar = next(p for p in elenco.json() if p["builtin_key"] == "tar")

    dettaglio = await api_client.get(f"/api/v1/severity-presets/{tar['id']}", headers=headers)
    regole_originali = dettaglio.json()["rules"]
    await api_client.delete(
        f"/api/v1/severity-preset-rules/{regole_originali[0]['id']}", headers=headers
    )
    await api_client.patch(
        f"/api/v1/severity-presets/{tar['id']}", json={"name": "tar modificato"}, headers=headers
    )

    ripristinato = await api_client.post(
        f"/api/v1/severity-presets/{tar['id']}/reset", headers=headers
    )
    assert ripristinato.status_code == 200, ripristinato.text
    assert ripristinato.json()["name"] == "tar"
    assert len(ripristinato.json()["rules"]) == len(regole_originali)
    assert [r["pattern"] for r in ripristinato.json()["rules"]] == [
        r["pattern"] for r in regole_originali
    ]


@pytest.mark.e2e
async def test_ripristino_su_preset_creato_a_mano_e_conflitto(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    preset = await _new_preset(
        api_client,
        headers,
        f"custom-{uuid.uuid4().hex[:6]}",
        [{"pattern": "QUALCOSA", "severity": "error"}],
    )

    resp = await api_client.post(f"/api/v1/severity-presets/{preset['id']}/reset", headers=headers)
    assert resp.status_code == 409


# --- precedenza e ordine ---------------------------------------------------


@pytest.mark.e2e
async def test_regola_del_receiver_vince_su_quella_del_preset(api_client, two_tenants, owner_token):
    """Un preset e condiviso: la regola scritta sul singolo receiver deve poterlo
    correggere senza doverlo duplicare."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    preset = await _new_preset(
        api_client,
        headers,
        f"p-{uuid.uuid4().hex[:6]}",
        [{"pattern": "MANUTENZIONE", "severity": "critical"}],
    )
    await _apply(api_client, headers, receiver["id"], [preset["id"]])

    # Su questo receiver la manutenzione e attesa: vale come avviso, non come
    # emergenza.
    await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/severity-rules",
        json={"pattern": "MANUTENZIONE", "severity": "warning"},
        headers=headers,
    )

    resp = await _ingest(api_client, receiver["slug"], "MANUTENZIONE programmata in corso")
    assert resp.json()["severity"] == "warning"
    assert resp.json()["severity_source"] == "rule"


@pytest.mark.e2e
async def test_ordine_dei_preset_decide_chi_vince(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    primo = await _new_preset(
        api_client,
        headers,
        f"a-{uuid.uuid4().hex[:6]}",
        [{"pattern": "CONTESO", "severity": "warning"}],
    )
    secondo = await _new_preset(
        api_client,
        headers,
        f"b-{uuid.uuid4().hex[:6]}",
        [{"pattern": "CONTESO", "severity": "critical"}],
    )

    await _apply(api_client, headers, receiver["id"], [primo["id"], secondo["id"]])
    assert (await _ingest(api_client, receiver["slug"], "evento CONTESO")).json()[
        "severity"
    ] == "warning"

    await _apply(api_client, headers, receiver["id"], [secondo["id"], primo["id"]])
    assert (await _ingest(api_client, receiver["slug"], "evento CONTESO")).json()[
        "severity"
    ] == "critical"


@pytest.mark.e2e
async def test_catena_effettiva_mostra_origine_e_ordine(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/severity-rules",
        json={"pattern": "LOCALE", "severity": "error"},
        headers=headers,
    )
    preset = await _new_preset(
        api_client,
        headers,
        f"p-{uuid.uuid4().hex[:6]}",
        [
            {"pattern": "DAL-PRESET-1", "severity": "critical"},
            {"pattern": "dal-preset-2", "severity": "warning"},
        ],
    )
    await _apply(api_client, headers, receiver["id"], [preset["id"]])

    resp = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/severity-chain", headers=headers
    )
    assert resp.status_code == 200, resp.text
    catena = resp.json()
    assert [r["pattern"] for r in catena] == ["LOCALE", "DAL-PRESET-1", "dal-preset-2"]
    assert [r["origin"] for r in catena] == ["receiver", "preset", "preset"]
    assert [r["position"] for r in catena] == [1, 2, 3]
    assert catena[1]["preset_name"] == preset["name"]
    assert catena[0]["preset_id"] is None


@pytest.mark.e2e
async def test_prova_severity_dice_quale_preset_ha_deciso(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    preset = await _new_preset(
        api_client,
        headers,
        f"p-{uuid.uuid4().hex[:6]}",
        [{"pattern": "DISCO PIENO", "severity": "critical"}],
    )
    await _apply(api_client, headers, receiver["id"], [preset["id"]])

    resp = await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/test-severity",
        json={"content": "attenzione: DISCO PIENO su /var"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["severity"] == "critical"
    assert resp.json()["source"] == "preset_rule"
    assert resp.json()["matched_preset_name"] == preset["name"]
    assert resp.json()["matched_preset_id"] == preset["id"]


@pytest.mark.e2e
async def test_regola_disattivata_nel_preset_non_scatta(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    preset = await _new_preset(
        api_client,
        headers,
        f"p-{uuid.uuid4().hex[:6]}",
        [{"pattern": "SPENTA", "severity": "critical"}],
    )
    dettaglio = await api_client.get(f"/api/v1/severity-presets/{preset['id']}", headers=headers)
    regola = dettaglio.json()["rules"][0]

    await api_client.patch(
        f"/api/v1/severity-preset-rules/{regola['id']}", json={"enabled": False}, headers=headers
    )
    await _apply(api_client, headers, receiver["id"], [preset["id"]])

    resp = await _ingest(api_client, receiver["slug"], "regola SPENTA")
    assert resp.json()["severity_source"] == "receiver_default"


# --- associazione ai receiver ----------------------------------------------


@pytest.mark.e2e
async def test_piu_preset_sullo_stesso_receiver(api_client, two_tenants, owner_token):
    """Il caso descritto dal committente: generico + tar + rclone sullo stesso
    receiver."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)
    elenco = (await api_client.get("/api/v1/severity-presets", headers=headers)).json()
    per_chiave = {p["builtin_key"]: p for p in elenco}

    receiver = await _make_receiver(api_client, headers, tenant_id)
    ids = [per_chiave["bash-generic"]["id"], per_chiave["tar"]["id"], per_chiave["rclone"]["id"]]
    resp = await _apply(api_client, headers, receiver["id"], ids)
    assert resp.status_code == 200, resp.text
    assert [p["preset_id"] for p in resp.json()] == ids
    assert [p["position"] for p in resp.json()] == [0, 1, 2]

    letti = await api_client.get(f"/api/v1/receivers/{receiver['id']}/presets", headers=headers)
    assert [p["builtin_key"] for p in letti.json()] == ["bash-generic", "tar", "rclone"]

    # Errore tipico di tar: lo riconosce il preset tar, non quello generico.
    tar_out = await _ingest(
        api_client, receiver["slug"], "tar: /dati/db.sql: Cannot open: No such file or directory"
    )
    assert tar_out.json()["severity"] == "error"
    assert tar_out.json()["severity_source"] == "preset_rule"


@pytest.mark.e2e
async def test_elenco_preset_sostituisce_il_precedente(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    uno = await _new_preset(
        api_client,
        headers,
        f"u-{uuid.uuid4().hex[:6]}",
        [{"pattern": "UNO", "severity": "error"}],
    )
    due = await _new_preset(
        api_client,
        headers,
        f"d-{uuid.uuid4().hex[:6]}",
        [{"pattern": "DUE", "severity": "error"}],
    )

    await _apply(api_client, headers, receiver["id"], [uno["id"], due["id"]])
    resp = await _apply(api_client, headers, receiver["id"], [due["id"]])
    assert [p["preset_id"] for p in resp.json()] == [due["id"]]

    assert (await _ingest(api_client, receiver["slug"], "solo UNO")).json()[
        "severity_source"
    ] == "receiver_default"

    # Elenco vuoto: stacca tutto.
    vuoto = await _apply(api_client, headers, receiver["id"], [])
    assert vuoto.json() == []


@pytest.mark.e2e
async def test_preset_duplicato_nella_richiesta_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    preset = await _new_preset(
        api_client,
        headers,
        f"p-{uuid.uuid4().hex[:6]}",
        [{"pattern": "X", "severity": "error"}],
    )

    resp = await _apply(api_client, headers, receiver["id"], [preset["id"], preset["id"]])
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_preset_inesistente_404(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)

    resp = await _apply(api_client, headers, receiver["id"], [str(uuid.uuid4())])
    assert resp.status_code == 404


@pytest.mark.e2e
async def test_preset_eliminato_lascia_il_receiver_coerente(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver = await _make_receiver(api_client, headers, tenant_id)
    preset = await _new_preset(
        api_client,
        headers,
        f"p-{uuid.uuid4().hex[:6]}",
        [{"pattern": "SPARIRA", "severity": "critical"}],
    )
    await _apply(api_client, headers, receiver["id"], [preset["id"]])

    assert (
        await api_client.delete(f"/api/v1/severity-presets/{preset['id']}", headers=headers)
    ).status_code == 204

    presets = await api_client.get(f"/api/v1/receivers/{receiver['id']}/presets", headers=headers)
    assert presets.json() == []
    resp = await _ingest(api_client, receiver["slug"], "il preset e SPARIRA-to")
    assert resp.json()["severity_source"] == "receiver_default"


# --- gestione del preset ---------------------------------------------------


@pytest.mark.e2e
async def test_nome_duplicato_409(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    nome = f"unico-{uuid.uuid4().hex[:6]}"
    await _new_preset(api_client, headers, nome, [])

    resp = await api_client.post(
        "/api/v1/severity-presets", json={"name": nome, "description": ""}, headers=headers
    )
    assert resp.status_code == 409


@pytest.mark.e2e
async def test_pattern_non_compilabile_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    preset = await _new_preset(api_client, headers, f"p-{uuid.uuid4().hex[:6]}", [])

    resp = await api_client.post(
        f"/api/v1/severity-presets/{preset['id']}/rules",
        json={"pattern": "(non chiuso", "severity": "error"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "RE2" in resp.json()["detail"]


@pytest.mark.e2e
async def test_priorita_assegnata_e_riordino(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    preset = await _new_preset(
        api_client,
        headers,
        f"p-{uuid.uuid4().hex[:6]}",
        [
            {"pattern": "PRIMA", "severity": "error"},
            {"pattern": "SECONDA", "severity": "warning"},
        ],
    )
    dettaglio = await api_client.get(f"/api/v1/severity-presets/{preset['id']}", headers=headers)
    regole = dettaglio.json()["rules"]
    assert [r["priority"] for r in regole] == [10, 20]

    # Priorita gia occupata: conflitto esplicito, non un 500 dal vincolo.
    conflitto = await api_client.post(
        f"/api/v1/severity-presets/{preset['id']}/rules",
        json={"pattern": "TERZA", "severity": "error", "priority": 10},
        headers=headers,
    )
    assert conflitto.status_code == 409

    riordino = await api_client.put(
        f"/api/v1/severity-presets/{preset['id']}/rules/order",
        json={"rule_ids": [regole[1]["id"], regole[0]["id"]]},
        headers=headers,
    )
    assert riordino.status_code == 200, riordino.text
    assert [r["pattern"] for r in riordino.json()] == ["SECONDA", "PRIMA"]
    assert [r["priority"] for r in riordino.json()] == [10, 20]


# --- permessi e isolamento -------------------------------------------------


@pytest.mark.e2e
async def test_member_applica_ma_non_modifica_i_preset(api_client, two_tenants, owner_token):
    """Un preset e condiviso fra gruppi: modificarlo tocca receiver che il member
    non gestisce. Applicarlo al proprio receiver invece e una scelta locale."""
    tenant_id, _ = two_tenants
    owner_headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"g-{uuid.uuid4().hex[:6]}")
    receiver = (
        await api_client.post(
            f"/api/v1/groups/{group_id}/receivers",
            json={"name": "r-member", "default_severity": "info"},
            headers=owner_headers,
        )
    ).json()
    preset = await _new_preset(
        api_client,
        owner_headers,
        f"p-{uuid.uuid4().hex[:6]}",
        [{"pattern": "X", "severity": "error"}],
    )

    email = f"member-{uuid.uuid4().hex[:8]}@test.com"
    creato = await api_client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": PASSWORD,
            "role": "member",
            "group_ids": [str(group_id)],
        },
        headers=owner_headers,
    )
    assert creato.status_code == 201, creato.text
    token = (
        await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    ).json()["access_token"]
    member_headers = {"Authorization": f"Bearer {token}"}

    assert (
        await api_client.get("/api/v1/severity-presets", headers=member_headers)
    ).status_code == 200
    assert (
        await api_client.post(
            "/api/v1/severity-presets",
            json={"name": f"vietato-{uuid.uuid4().hex[:6]}", "description": ""},
            headers=member_headers,
        )
    ).status_code == 403
    assert (
        await api_client.patch(
            f"/api/v1/severity-presets/{preset['id']}",
            json={"name": "rinominato dal member"},
            headers=member_headers,
        )
    ).status_code == 403

    applicato = await _apply(api_client, member_headers, receiver["id"], [preset["id"]])
    assert applicato.status_code == 200, applicato.text


@pytest.mark.e2e
async def test_preset_non_attraversano_i_tenant(api_client, two_tenants, owner_token):
    tenant_a, tenant_b = two_tenants
    headers_a = await _headers(api_client, tenant_a, owner_token)
    headers_b = await _headers(api_client, tenant_b, owner_token)

    preset = await _new_preset(
        api_client,
        headers_a,
        f"solo-a-{uuid.uuid4().hex[:6]}",
        [{"pattern": "RISERVATO", "severity": "critical"}],
    )

    visti_da_b = await api_client.get("/api/v1/severity-presets", headers=headers_b)
    assert preset["id"] not in [p["id"] for p in visti_da_b.json()]
    assert (
        await api_client.get(f"/api/v1/severity-presets/{preset['id']}", headers=headers_b)
    ).status_code == 404

    receiver_b = await _make_receiver(api_client, headers_b, tenant_b)
    assert (
        await _apply(api_client, headers_b, receiver_b["id"], [preset["id"]])
    ).status_code == 404
