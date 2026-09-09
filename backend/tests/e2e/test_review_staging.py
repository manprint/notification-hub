"""E2E delle regressioni trovate nella revisione pre-staging.

Vedi docs/REVIEW.md, sezione "Verifica 3": difetti di autorizzazione, di
protocollo HTTP e filtri di stato mai implementati.
"""

import uuid

import pytest

from tests.conftest_factories import create_group, create_receiver

PASSWORD = "correct-horse-battery"  # noqa: S105


async def _login(api_client, email: str) -> str:
    resp = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _create_user(api_client, owner_headers, email: str, role: str, group_ids: list) -> dict:
    resp = await api_client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": PASSWORD,
            "role": role,
            "group_ids": [str(g) for g in group_ids],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.e2e
async def test_content_length_descrive_i_byte_inviati_non_il_corpo_originale(
    api_client, two_tenants, owner_token
):
    """`content_size` e la dimensione del corpo ORIGINALE; il download inline
    manda il testo NORMALIZZATO (UTF-8 non valido sostituito con U+FFFD, byte
    NUL rimossi, spec 6.2), che ha un'altra lunghezza in byte. Dichiarare
    content_size come Content-Length fa troncare la risposta o fallire il
    client: sono 10 byte in ingresso e 12 in uscita."""
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    raw = b"prima\xffdopo"  # 10 byte, uno non decodificabile
    ingest = await api_client.post(f"/ingest/{slug}", content=raw)
    assert ingest.status_code == 201, ingest.text
    notification_id = ingest.json()["id"]

    detail = await api_client.get(f"/api/v1/notifications/{notification_id}", headers=headers)
    assert detail.json()["content_normalized"] is True
    assert detail.json()["content_size"] == len(raw) == 10

    content = await api_client.get(
        f"/api/v1/notifications/{notification_id}/content", headers=headers
    )
    assert content.status_code == 200
    atteso = "prima�dopo".encode()
    assert len(atteso) == 12
    assert int(content.headers["content-length"]) == len(atteso)
    assert content.content == atteso


@pytest.mark.e2e
async def test_viewer_non_puo_marcare_letta_ne_verificata(api_client, two_tenants, owner_token):
    """Un viewer ha accesso in sola lettura (spec 3, ruoli). PATCH e bulk-read
    stavano su `current_claims` con `write=False`: un viewer poteva marcare come
    letta o verificata qualunque notifica dei gruppi che gli sono visibili."""
    tenant_id, _ = two_tenants
    owner_headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, f"g-{uuid.uuid4().hex[:6]}")
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, group_id)

    ingest = await api_client.post(f"/ingest/{slug}", content="qualcosa")
    notification_id = ingest.json()["id"]

    email = f"viewer-{uuid.uuid4().hex[:8]}@test.com"
    await _create_user(api_client, owner_headers, email, "viewer", [group_id])
    viewer_headers = {"Authorization": f"Bearer {await _login(api_client, email)}"}

    # Legge: deve continuare a funzionare.
    lista = await api_client.get(
        "/api/v1/notifications", params={"receiver_id": str(receiver_id)}, headers=viewer_headers
    )
    assert lista.status_code == 200
    assert len(lista.json()["notifications"]) == 1

    # Scrive: no.
    patch_status = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "read"}, headers=viewer_headers
    )
    assert patch_status.status_code == 403, patch_status.text

    patch_verified = await api_client.patch(
        f"/api/v1/notifications/{notification_id}",
        json={"verified": True},
        headers=viewer_headers,
    )
    assert patch_verified.status_code == 403, patch_verified.text

    bulk = await api_client.post(
        "/api/v1/notifications/bulk-read",
        json={"group_id": str(group_id)},
        headers=viewer_headers,
    )
    assert bulk.status_code == 403, bulk.text

    delete = await api_client.delete(
        f"/api/v1/notifications/{notification_id}", headers=viewer_headers
    )
    assert delete.status_code == 403, delete.text

    # E niente e' cambiato davvero.
    detail = await api_client.get(f"/api/v1/notifications/{notification_id}", headers=owner_headers)
    assert detail.json()["status"] == "unread"
    assert detail.json()["verified"] is False


@pytest.mark.e2e
async def test_filtro_verified_indipendente_da_status(api_client, two_tenants, owner_token):
    """`.planning/ROADMAP.md` fase 3: read e verified sono due dimensioni
    filtrabili separatamente e combinabili. Il filtro `verified` non esisteva:
    l'unico modo di isolare le notifiche da rivedere era guardarle a occhio."""
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    prima = (await api_client.post(f"/ingest/{slug}", content="prima")).json()["id"]
    (await api_client.post(f"/ingest/{slug}", content="seconda")).json()

    patch = await api_client.patch(
        f"/api/v1/notifications/{prima}", json={"verified": True}, headers=headers
    )
    assert patch.status_code == 200

    async def _ids(**params) -> list[str]:
        resp = await api_client.get(
            "/api/v1/notifications",
            params={"receiver_id": str(receiver_id), **params},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        return [n["id"] for n in resp.json()["notifications"]]

    assert await _ids(verified="true") == [prima]
    assert prima not in await _ids(verified="false")
    assert len(await _ids(verified="false")) == 1
    assert len(await _ids()) == 2

    # Le due dimensioni si combinano: `verified` non tocca read/unread.
    assert await _ids(verified="true", status="unread") == [prima]
    assert await _ids(verified="true", status="read") == []


@pytest.mark.e2e
async def test_bulk_read_rispetta_il_filtro_verified(api_client, two_tenants, owner_token):
    """Con il filtro "solo non verificate" attivo, "segna tutte come lette" non
    deve toccare quelle gia verificate: sono fuori dalla vista."""
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    verificata = (await api_client.post(f"/ingest/{slug}", content="una")).json()["id"]
    await api_client.post(f"/ingest/{slug}", content="due")
    await api_client.patch(
        f"/api/v1/notifications/{verificata}", json={"verified": True}, headers=headers
    )

    bulk = await api_client.post(
        "/api/v1/notifications/bulk-read",
        json={"receiver_id": str(receiver_id), "verified": False},
        headers=headers,
    )
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["marked_read"] == 1

    detail = await api_client.get(f"/api/v1/notifications/{verificata}", headers=headers)
    assert detail.json()["status"] == "unread"


@pytest.mark.e2e
async def test_rate_limit_del_login_separato_per_ip_dietro_un_proxy_fidato(
    api_client, two_tenants, monkeypatch
):
    """Il limite e su (email, IP) apposta: sulla sola email chiunque conosca un
    indirizzo puo bloccare quell'account. Dietro nginx `request.client.host` e
    l'IP del proxy per TUTTI, quindi senza risolvere X-Forwarded-For la chiave
    tornava a essere di fatto la sola email."""
    from app.api import deps
    from app.core.config import get_settings

    # 127.0.0.1 e l'indirizzo che httpx.ASGITransport mette nello scope: qui fa
    # le veci del reverse proxy davanti all'API.
    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: get_settings().model_copy(update={"trusted_proxies": "127.0.0.1"}),
    )

    email = f"bersaglio-{uuid.uuid4().hex[:10]}@test.com"
    attaccante = {"X-Forwarded-For": "203.0.113.10"}
    vittima = {"X-Forwarded-For": "203.0.113.20"}

    for tentativo in range(10):
        resp = await api_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "sbagliata-ma-lunga"},
            headers=attaccante,
        )
        assert resp.status_code == 401, f"tentativo {tentativo}: {resp.status_code}"

    esaurito = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "sbagliata-ma-lunga"},
        headers=attaccante,
    )
    assert esaurito.status_code == 429

    # Stessa email, altro IP: budget separato, l'account non e bloccato.
    altro_ip = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "sbagliata-ma-lunga"},
        headers=vittima,
    )
    assert altro_ip.status_code == 401, altro_ip.text


@pytest.mark.e2e
async def test_content_type_non_supportato_dice_quali_sono_accettati(api_client, two_tenants):
    """Il 415 elencava solo text/plain mentre l'endpoint accetta anche
    application/x-www-form-urlencoded e l'assenza di Content-Type: il messaggio
    mandava a cercare un problema che non c'era."""
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    resp = await api_client.post(
        f"/ingest/{slug}", content=b"{}", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 415
    detail = resp.json()["detail"]
    assert "text/plain" in detail
    assert "application/x-www-form-urlencoded" in detail
