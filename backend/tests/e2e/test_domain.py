"""E2E per la gestione di dominio: receiver, severity-rules, channel, tenant
(spec 9.3, 9.4)."""

import uuid

import pytest


@pytest.mark.e2e
async def test_receiver_lifecycle_e_rotate_slug(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Group {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert group_resp.status_code == 201
    group_id = group_resp.json()["id"]

    receiver_resp = await api_client.post(
        f"/api/v1/groups/{group_id}/receivers",
        json={"name": "Backup notturno"},
        headers=headers,
    )
    assert receiver_resp.status_code == 201
    receiver = receiver_resp.json()
    assert len(receiver["slug"]) == 22
    receiver_id = receiver["id"]
    old_slug = receiver["slug"]

    rotate_resp = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/rotate-slug", headers=headers
    )
    assert rotate_resp.status_code == 200
    assert rotate_resp.json()["slug"] != old_slug

    disable_resp = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"status": "disabled"}, headers=headers
    )
    assert disable_resp.status_code == 200
    assert disable_resp.json()["status"] == "disabled"


@pytest.mark.e2e
async def test_severity_rule_pattern_non_valido_ritorna_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Group {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    group_id = group_resp.json()["id"]
    receiver_resp = await api_client.post(
        f"/api/v1/groups/{group_id}/receivers", json={"name": "R"}, headers=headers
    )
    receiver_id = receiver_resp.json()["id"]

    # backreference: non supportato da RE2 (spec 4.2)
    response = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/severity-rules",
        json={"priority": 1, "pattern": r"(a)\1", "severity": "error"},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.e2e
async def test_test_severity_endpoint(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Group {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    group_id = group_resp.json()["id"]
    receiver_resp = await api_client.post(
        f"/api/v1/groups/{group_id}/receivers", json={"name": "R"}, headers=headers
    )
    receiver_id = receiver_resp.json()["id"]

    await api_client.post(
        f"/api/v1/receivers/{receiver_id}/severity-rules",
        json={"priority": 1, "pattern": "FALLITO", "severity": "error"},
        headers=headers,
    )

    response = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/test-severity",
        json={"content": "Backup FALLITO"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["severity"] == "error"
    assert response.json()["source"] == "rule"
    assert response.json()["matched_pattern"] == "FALLITO"


@pytest.mark.e2e
async def test_channel_non_espone_mai_il_webhook_in_chiaro(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    secret_url = "https://hooks.slack.com/services/T00/B00/XXXXSECRETXXXX"
    response = await api_client.post(
        "/api/v1/channels",
        json={"name": "Slack #ops", "type": "slack", "webhook_url": secret_url},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert "webhook_url" not in body
    assert secret_url not in str(body)
    assert "webhook_hint" in body

    list_response = await api_client.get("/api/v1/channels", headers=headers)
    assert secret_url not in list_response.text


@pytest.mark.e2e
async def test_abbassare_cap_tenant_sotto_receiver_esistente_409(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Group {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    group_id = group_resp.json()["id"]
    await api_client.post(
        f"/api/v1/groups/{group_id}/receivers",
        json={"name": "R", "max_body_bytes": 1_000_000},
        headers=headers,
    )

    response = await api_client.patch(
        "/api/v1/tenant", json={"max_body_bytes": 500_000}, headers=headers
    )
    assert response.status_code == 409
    conflicting = response.json()["conflicting_receivers"]
    assert conflicting == [{"name": "R", "max_body_bytes": 1_000_000}]


@pytest.mark.e2e
async def test_cancellazione_gruppo_richiede_conferma_per_nome(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    name = f"Group {uuid.uuid4().hex[:8]}"
    group_resp = await api_client.post("/api/v1/groups", json={"name": name}, headers=headers)
    group_id = group_resp.json()["id"]

    wrong_confirm = await api_client.delete(
        f"/api/v1/groups/{group_id}", params={"confirm": "wrong-name"}, headers=headers
    )
    assert wrong_confirm.status_code == 422

    right_confirm = await api_client.delete(
        f"/api/v1/groups/{group_id}", params={"confirm": name}, headers=headers
    )
    assert right_confirm.status_code == 204


@pytest.mark.e2e
async def test_delete_impact_conta_receiver_del_gruppo(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Group {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    group_id = group_resp.json()["id"]
    await api_client.post(
        f"/api/v1/groups/{group_id}/receivers", json={"name": "R1"}, headers=headers
    )
    await api_client.post(
        f"/api/v1/groups/{group_id}/receivers", json={"name": "R2"}, headers=headers
    )

    response = await api_client.get(f"/api/v1/groups/{group_id}/delete-impact", headers=headers)
    assert response.status_code == 200
    assert response.json()["receivers"] == 2
