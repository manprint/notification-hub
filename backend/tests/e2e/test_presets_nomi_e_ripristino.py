"""E2E: nomi occupati e ripristino dei preset predefiniti.

Un preset personalizzato chiamato come un predefinito mancante non deve far
fallire il sync di tutto il tenant; un ripristino che collide con un nome
esistente, o di un predefinito non piu nel catalogo, deve dire il motivo.
"""

import uuid

import pytest
from sqlalchemy import update

from app.db.session import tenant_session
from app.models.severity_preset import SeverityPreset
from tests.e2e.test_severity_presets import _headers, _new_preset


@pytest.mark.e2e
async def test_sync_salta_il_nome_gia_usato_e_installa_il_resto(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)
    elenco = (await api_client.get("/api/v1/severity-presets", headers=headers)).json()
    for chiave in ("tar", "postgres"):
        copia = next(p for p in elenco if p["builtin_key"] == chiave)
        cancellata = await api_client.delete(
            f"/api/v1/severity-presets/{copia['id']}", headers=headers
        )
        assert cancellata.status_code == 204, cancellata.text
    await _new_preset(api_client, headers, "tar", [{"pattern": "TAR", "severity": "error"}])

    resp = await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["skipped"] == ["tar"]
    assert "postgres" in corpo["installed"]
    assert "tar" not in corpo["installed"]

    elenco = (await api_client.get("/api/v1/severity-presets", headers=headers)).json()
    copie_tar = [p for p in elenco if p["name"] == "tar"]
    assert len(copie_tar) == 1
    assert copie_tar[0]["builtin_key"] is None


@pytest.mark.e2e
async def test_ripristino_con_nome_occupato_dice_quale_nome(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    await api_client.post("/api/v1/severity-presets/sync-builtin", headers=headers)
    elenco = (await api_client.get("/api/v1/severity-presets", headers=headers)).json()
    tar = next(p for p in elenco if p["builtin_key"] == "tar")
    rinomina = await api_client.patch(
        f"/api/v1/severity-presets/{tar['id']}", json={"name": "tar copia"}, headers=headers
    )
    assert rinomina.status_code == 200, rinomina.text
    await _new_preset(api_client, headers, "tar", [{"pattern": "TAR", "severity": "error"}])

    resp = await api_client.post(f"/api/v1/severity-presets/{tar['id']}/reset", headers=headers)
    assert resp.status_code == 409, resp.text
    assert "'tar'" in resp.json()["detail"]


@pytest.mark.e2e
async def test_ripristino_di_un_predefinito_ritirato_dice_che_non_e_piu_nel_catalogo(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    nome = f"ritirato-{uuid.uuid4().hex[:6]}"
    preset = await _new_preset(api_client, headers, nome, [{"pattern": "X", "severity": "error"}])
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(SeverityPreset)
            .where(SeverityPreset.id == uuid.UUID(preset["id"]))
            .values(builtin_key="voce-che-non-esiste")
        )

    resp = await api_client.post(f"/api/v1/severity-presets/{preset['id']}/reset", headers=headers)
    assert resp.status_code == 409, resp.text
    assert "no longer in the catalog" in resp.json()["detail"]
