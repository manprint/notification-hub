"""E2E: il PUT su MinIO non tiene una connessione del pool applicativo (spec 6.5).

Con un body oltre la soglia inline il PUT avviene prima del commit, ma non
dentro la transazione: una connessione tenuta aperta per tutto l'upload
bloccherebbe il pool (e il lock di quota) se lo storage rallenta.
"""

import uuid

import pytest

from tests.conftest_factories import create_receiver


@pytest.mark.e2e
async def test_il_put_su_minio_non_occupa_una_connessione_del_pool(
    api_client, two_tenants, monkeypatch
):
    from app.db.session import engine_app
    from app.services import storage

    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=2 * 1024 * 1024)
    # La baseline include le connessioni che il test stesso tiene aperte (owner_conn).
    connessioni_prima_della_richiesta = engine_app.pool.checkedout()
    connessioni_durante_il_put: list[int] = []

    async def _put_registra_il_pool(key: str, body: bytes) -> None:
        connessioni_durante_il_put.append(engine_app.pool.checkedout())

    monkeypatch.setattr(storage, "upload_object", _put_registra_il_pool)

    response = await api_client.post(f"/ingest/{slug}", content="x" * (1024 * 1024 + 1))

    assert response.status_code == 201
    assert response.json()["storage_backend"] == "object"
    assert connessioni_durante_il_put == [connessioni_prima_della_richiesta]
