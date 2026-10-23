"""E2E: il 409 di PATCH /tenant distingue i receiver con lo stesso nome in gruppi diversi
(residuo 150). Il nome e' unico solo dentro il gruppo: senza id e gruppo il client non puo'
dire quale receiver deve cambiare."""

import uuid

import pytest


@pytest.mark.e2e
async def test_conflitti_con_lo_stesso_nome_in_gruppi_diversi_hanno_id_distinti(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    attesi = {}
    for _ in range(2):
        nome_gruppo = f"Group {uuid.uuid4().hex[:8]}"
        group_resp = await api_client.post(
            "/api/v1/groups", json={"name": nome_gruppo}, headers=headers
        )
        receiver_resp = await api_client.post(
            f"/api/v1/groups/{group_resp.json()['id']}/receivers",
            json={"name": "Backup", "max_body_bytes": 1_000_000},
            headers=headers,
        )
        assert receiver_resp.status_code == 201, receiver_resp.text
        attesi[receiver_resp.json()["id"]] = nome_gruppo

    response = await api_client.patch(
        "/api/v1/tenant", json={"max_body_bytes": 500_000}, headers=headers
    )

    assert response.status_code == 409
    conflicting = response.json()["conflicting_receivers"]
    assert len(conflicting) == 2
    assert {riga["id"] for riga in conflicting} == set(attesi)
    for riga in conflicting:
        assert riga["name"] == "Backup"
        assert riga["group_name"] == attesi[riga["id"]]
        assert riga["max_body_bytes"] == 1_000_000
