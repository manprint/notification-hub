"""E2E: il bind di un canale a un gruppo risponde 201 alla creazione e 200 all'aggiornamento
della stessa coppia, come l'override di canale su receiver (c-be-api-05)."""

import uuid

import pytest

from tests.conftest_factories import create_group


@pytest.mark.e2e
async def test_bind_ripetuto_sulla_stessa_coppia_risponde_200(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, name=f"Gruppo {uuid.uuid4().hex[:6]}")
    channel = await api_client.post(
        "/api/v1/channels",
        json={
            "name": f"Slack {uuid.uuid4().hex[:6]}",
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/T0/B0/X0",
        },
        headers=headers,
    )
    assert channel.status_code == 201, channel.text
    channel_id = channel.json()["id"]
    url = f"/api/v1/groups/{group_id}/channels"

    creazione = await api_client.post(
        url, json={"channel_id": channel_id, "min_severity": "info"}, headers=headers
    )
    assert creazione.status_code == 201, creazione.text

    aggiornamento = await api_client.post(
        url, json={"channel_id": channel_id, "min_severity": "error"}, headers=headers
    )
    assert aggiornamento.status_code == 200, aggiornamento.text
    assert aggiornamento.json()["min_severity"] == "error"
