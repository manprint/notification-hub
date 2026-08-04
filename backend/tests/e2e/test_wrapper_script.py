"""E2E dello slug parlante e del download dello script wrapper precompilato.

Il filo conduttore e' uno: l'indirizzo che l'operatore si porta a casa deve
essere quello a cui l'istanza risponde davvero, anche dietro reverse proxy in
https, e deve funzionare per l'ingestion senza altri passaggi.
"""

import uuid

import pytest

PROXY_HEADERS = {"host": "notifyhub.com", "x-forwarded-proto": "https"}


async def _gruppo_e_receiver(
    api_client, headers, *, group_name="Maritime", receiver_name="elog-test"
):
    group_resp = await api_client.post(
        "/api/v1/groups",
        json={"name": f"{group_name} {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    receiver_resp = await api_client.post(
        f"/api/v1/groups/{group_id}/receivers",
        json={"name": receiver_name},
        headers=headers,
    )
    assert receiver_resp.status_code == 201
    return group_id, receiver_resp.json()


@pytest.mark.e2e
async def test_slug_parlante_contiene_gruppo_e_receiver(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, receiver = await _gruppo_e_receiver(
        api_client, headers, group_name="Maritime", receiver_name="eLog Test"
    )
    slug = receiver["slug"]
    assert slug.startswith("maritime-")
    assert "-elog-test-" in slug
    assert len(slug.rsplit("-elog-test-", 1)[1]) == 22


@pytest.mark.e2e
async def test_ingestion_funziona_con_lo_slug_parlante(api_client, two_tenants, owner_token):
    """La forma dello slug cambia, l'endpoint no: e' il test che dimostra che
    non c'e' regressione sull'unica cosa che conta."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, receiver = await _gruppo_e_receiver(api_client, headers)

    ingest_resp = await api_client.post(f"/ingest/{receiver['slug']}", content="Backup completato")
    assert ingest_resp.status_code == 201


@pytest.mark.e2e
async def test_ingest_url_segue_il_reverse_proxy(api_client, two_tenants, owner_token):
    """`NOTIFYHUB_PUBLIC_BASE_URL` in .env.test punta al loopback: l'URL deve
    allora venire dalla richiesta, header del proxy compresi."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, receiver = await _gruppo_e_receiver(api_client, headers)

    detail = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}", headers={**headers, **PROXY_HEADERS}
    )
    assert detail.status_code == 200
    assert detail.json()["ingest_url"] == f"https://notifyhub.com/ingest/{receiver['slug']}"


@pytest.mark.e2e
async def test_ingest_url_presente_anche_negli_elenchi(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_id, receiver = await _gruppo_e_receiver(api_client, headers)

    del_gruppo = await api_client.get(
        f"/api/v1/groups/{group_id}/receivers", headers={**headers, **PROXY_HEADERS}
    )
    assert del_gruppo.status_code == 200
    assert del_gruppo.json()[0]["ingest_url"].startswith("https://notifyhub.com/ingest/")

    tutti = await api_client.get("/api/v1/receivers", headers={**headers, **PROXY_HEADERS})
    assert tutti.status_code == 200
    nostro = next(r for r in tutti.json() if r["id"] == receiver["id"])
    assert nostro["ingest_url"] == f"https://notifyhub.com/ingest/{receiver['slug']}"


@pytest.mark.e2e
async def test_download_script_precompilato(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, receiver = await _gruppo_e_receiver(api_client, headers)

    resp = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/wrapper-script",
        headers={**headers, **PROXY_HEADERS},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/x-shellscript")
    assert (
        resp.headers["content-disposition"] == 'attachment; filename="notifyhub-run-elog-test.sh"'
    )
    # Contiene una credenziale: non deve finire in nessuna cache.
    assert resp.headers["cache-control"] == "no-store"

    script = resp.text
    assert script.startswith("#!/bin/bash")
    assert 'URL="${NOTIFYHUB_URL:-https://notifyhub.com}"' in script
    assert f'SLUG="${{NOTIFYHUB_SLUG:-{receiver["slug"]}}}"' in script
    assert "Precompilato dalla dashboard" in script
    # L'URL nello script e quella esposta dall'API sono lo stesso indirizzo.
    detail = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}", headers={**headers, **PROXY_HEADERS}
    )
    assert detail.json()["ingest_url"] == f"https://notifyhub.com/ingest/{receiver['slug']}"


@pytest.mark.e2e
async def test_download_script_senza_header_di_proxy(api_client, two_tenants, owner_token):
    """Senza proxy davanti, l'URL viene dall'host della richiesta: lo script
    resta coerente con l'indirizzo da cui e' stato scaricato."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, receiver = await _gruppo_e_receiver(api_client, headers)

    resp = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/wrapper-script", headers=headers
    )
    assert resp.status_code == 200
    assert 'URL="${NOTIFYHUB_URL:-http://' in resp.text


@pytest.mark.e2e
async def test_download_script_dopo_rotate_slug(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, receiver = await _gruppo_e_receiver(api_client, headers)
    rotate = await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/rotate-slug", headers=headers
    )
    assert rotate.status_code == 200
    nuovo_slug = rotate.json()["slug"]

    resp = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/wrapper-script", headers=headers
    )
    assert f"NOTIFYHUB_SLUG:-{nuovo_slug}" in resp.text
    assert receiver["slug"] not in resp.text


@pytest.mark.e2e
async def test_download_script_di_un_altro_tenant_404(api_client, two_tenants, owner_token):
    tenant_a, tenant_b = two_tenants
    token_a = await owner_token(api_client, tenant_a)
    token_b = await owner_token(api_client, tenant_b)

    _, receiver = await _gruppo_e_receiver(api_client, {"Authorization": f"Bearer {token_a}"})

    resp = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/wrapper-script",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


@pytest.mark.e2e
async def test_download_script_senza_autenticazione_401(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    _, receiver = await _gruppo_e_receiver(api_client, {"Authorization": f"Bearer {token}"})

    resp = await api_client.get(f"/api/v1/receivers/{receiver['id']}/wrapper-script")
    assert resp.status_code == 401


@pytest.mark.e2e
async def test_rename_non_cambia_lo_slug(api_client, two_tenants, owner_token):
    """Rinominare non deve spegnere i cron che stanno inviando: lo slug resta
    quello, e si riallinea solo con rotate-slug."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, receiver = await _gruppo_e_receiver(api_client, headers)

    patch = await api_client.patch(
        f"/api/v1/receivers/{receiver['id']}",
        json={"name": "elog-produzione"},
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["slug"] == receiver["slug"]

    rotate = await api_client.post(
        f"/api/v1/receivers/{receiver['id']}/rotate-slug", headers=headers
    )
    assert "-elog-produzione-" in rotate.json()["slug"]


@pytest.mark.e2e
async def test_receiver_con_nome_non_traducibile(api_client, two_tenants, owner_token):
    """Nome fatto di soli caratteri non ASCII: lo slug perde il prefisso ma
    resta valido, e l'ingestion funziona."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    _, receiver = await _gruppo_e_receiver(api_client, headers, group_name="🚢", receiver_name="🚢")
    ingest_resp = await api_client.post(f"/ingest/{receiver['slug']}", content="ok")
    assert ingest_resp.status_code == 201

    resp = await api_client.get(
        f"/api/v1/receivers/{receiver['id']}/wrapper-script", headers=headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == 'attachment; filename="notifyhub-run.sh"'
