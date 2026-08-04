"""Forma delle risposte d'errore: RFC 7807 su tutta la superficie HTTP.

Questo file conteneva due test placebo (`GET /healthz`, assert 200) con un commento
che diceva "per ora verifichiamo che healthz funzioni": erano verdi e non
verificavano niente di cio' che promettevano. Un test che non puo' fallire e' peggio
di un test mancante, perche' fa credere coperto un comportamento che non lo e'.

Il contratto vero: ogni errore esce come `application/problem+json` con `type`,
`title`, `status`, `detail`. La dashboard usa `detail` per i messaggi e `type` per
distinguere i casi (`ErrorBanner` in frontend), quindi cambiarne la forma rompe la
UI senza rompere nessun test di endpoint.
"""

import uuid

import pytest

CAMPI_PROBLEM = {"type", "title", "status", "detail"}


def _e_un_problem(resp, status: int) -> dict:
    assert resp.status_code == status, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json"), (
        f"content-type inatteso: {resp.headers.get('content-type')}"
    )
    corpo = resp.json()
    assert CAMPI_PROBLEM <= set(corpo), f"campi mancanti: {CAMPI_PROBLEM - set(corpo)}"
    assert corpo["status"] == status
    assert corpo["type"].startswith("/problems/")
    assert isinstance(corpo["detail"], str)
    return corpo


@pytest.mark.e2e
async def test_422_su_corpo_non_valido(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)

    resp = await api_client.post(
        "/api/v1/groups",
        json={"nome_sbagliato": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    corpo = _e_un_problem(resp, 422)
    # L'elenco degli errori di campo e' serializzabile: un `ctx` con dentro
    # un'eccezione faceva uscire 500 al posto del 422 (difetto gia' corretto,
    # qui resta chiuso).
    assert "errors" in corpo
    assert isinstance(corpo["errors"], list)
    assert corpo["errors"], "nessun dettaglio sul campo rifiutato"


@pytest.mark.e2e
async def test_401_senza_credenziali(api_client):
    resp = await api_client.get("/api/v1/groups")
    _e_un_problem(resp, 401)


@pytest.mark.e2e
async def test_401_con_token_inventato(api_client):
    resp = await api_client.get(
        "/api/v1/groups", headers={"Authorization": "Bearer token-inventato"}
    )
    _e_un_problem(resp, 401)


@pytest.mark.e2e
async def test_404_su_risorsa_inesistente(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    resp = await api_client.get(
        f"/api/v1/receivers/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"}
    )
    _e_un_problem(resp, 404)


@pytest.mark.e2e
async def test_404_su_rotta_inesistente(api_client):
    """Anche una rotta che non esiste deve rispondere nella stessa forma: la SPA
    non deve trovarsi un corpo diverso solo perche' ha sbagliato percorso."""
    resp = await api_client.get("/api/v1/questa-rotta-non-esiste")
    _e_un_problem(resp, 404)


@pytest.mark.e2e
async def test_405_su_metodo_sbagliato(api_client):
    resp = await api_client.delete("/healthz")
    _e_un_problem(resp, 405)


@pytest.mark.e2e
async def test_413_su_corpo_oltre_il_limite(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    gruppo = await api_client.post(
        "/api/v1/groups", json={"name": f"Errori {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    receiver = await api_client.post(
        f"/api/v1/groups/{gruppo.json()['id']}/receivers",
        json={"name": "job", "max_body_bytes": 100},
        headers=headers,
    )
    slug = receiver.json()["slug"]

    resp = await api_client.post(f"/ingest/{slug}", content="x" * 200)
    _e_un_problem(resp, 413)


@pytest.mark.e2e
async def test_415_su_content_type_non_supportato(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    gruppo = await api_client.post(
        "/api/v1/groups", json={"name": f"Errori {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    receiver = await api_client.post(
        f"/api/v1/groups/{gruppo.json()['id']}/receivers", json={"name": "job"}, headers=headers
    )

    resp = await api_client.post(
        f"/ingest/{receiver.json()['slug']}",
        content=b'{"non": "supportato"}',
        headers={"Content-Type": "application/json"},
    )
    _e_un_problem(resp, 415)


@pytest.mark.e2e
async def test_il_detail_non_espone_dettagli_interni(api_client, two_tenants, owner_token):
    """`detail` finisce sotto gli occhi dell'utente in dashboard: non deve
    contenere nomi di tabelle, percorsi di file o tracce dello stack."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    risposte = [
        await api_client.get(f"/api/v1/receivers/{uuid.uuid4()}", headers=headers),
        await api_client.get("/api/v1/groups"),
        await api_client.post("/api/v1/groups", json={}, headers=headers),
    ]
    for resp in risposte:
        testo = resp.text.lower()
        for spia in ("traceback", "site-packages", "/home/", "psycopg", "sqlalchemy"):
            assert spia not in testo, f"{spia} esposto in {resp.status_code}: {resp.text[:200]}"
