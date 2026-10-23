"""E2E: l'ingestion inline fa una sola verifica di quota, in una sola transazione; quella
con oggetto su MinIO ne fa due, col PUT in mezzo (c-be-api-02).

Il conteggio e' sulla chiamata a enforce_tenant_quotas: ogni chiamata rilegge i totali
del tenant, quindi due chiamate sul percorso inline erano lavoro doppio senza motivo.
"""

import uuid

import pytest

from tests.conftest_factories import create_receiver


@pytest.mark.e2e
async def test_ingest_inline_verifica_la_quota_una_volta_sola(api_client, two_tenants, monkeypatch):
    from app.api import ingest as ingest_module

    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    chiamate: list[int] = []
    verifica_reale = ingest_module.enforce_tenant_quotas

    async def _verifica_registrata(session, tenant_id_, incoming_bytes):  # noqa: ANN001, ANN202
        chiamate.append(incoming_bytes)
        return await verifica_reale(session, tenant_id_, incoming_bytes)

    monkeypatch.setattr(ingest_module, "enforce_tenant_quotas", _verifica_registrata)

    response = await api_client.post(f"/ingest/{slug}", content="messaggio breve")

    assert response.status_code == 201, response.text
    assert response.json()["storage_backend"] == "inline"
    assert len(chiamate) == 1


@pytest.mark.e2e
async def test_ingest_con_oggetto_verifica_la_quota_prima_e_dopo_il_put(
    api_client, two_tenants, monkeypatch
):
    from app.api import ingest as ingest_module
    from app.services import storage

    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=2 * 1024 * 1024)
    eventi: list[str] = []
    verifica_reale = ingest_module.enforce_tenant_quotas

    async def _verifica_registrata(session, tenant_id_, incoming_bytes):  # noqa: ANN001, ANN202
        eventi.append("quota")
        return await verifica_reale(session, tenant_id_, incoming_bytes)

    async def _put_registrato(key: str, body: bytes) -> None:
        eventi.append("put")

    monkeypatch.setattr(ingest_module, "enforce_tenant_quotas", _verifica_registrata)
    monkeypatch.setattr(storage, "upload_object", _put_registrato)

    response = await api_client.post(f"/ingest/{slug}", content="x" * (1024 * 1024 + 1))

    assert response.status_code == 201, response.text
    assert response.json()["storage_backend"] == "object"
    assert eventi == ["quota", "put", "quota"]
