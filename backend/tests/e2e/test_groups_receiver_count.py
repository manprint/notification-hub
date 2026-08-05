"""E2E: receiver_count nei group payload.

T-GRP1 — la lista gruppi e il gruppo singolo devono riportare il numero di
receiver configurati, e un gruppo appena creato parte da 0."""

import uuid

import pytest

from tests.conftest_factories import create_group, create_receiver


@pytest.mark.e2e
async def test_groups_receiver_count_list_and_detail(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}

    group_id = await create_group(tenant_id, "rc-group")
    await create_receiver(tenant_id, f"rc-{uuid.uuid4().hex[:8]}", group_id=group_id)
    await create_receiver(tenant_id, f"rc2-{uuid.uuid4().hex[:8]}", group_id=group_id)
    empty_group_id = await create_group(tenant_id, "empty-group")

    resp = await api_client.get("/api/v1/groups", headers=headers)
    assert resp.status_code == 200, resp.text
    by_id = {g["id"]: g for g in resp.json()}
    assert by_id[str(group_id)]["receiver_count"] == 2
    assert by_id[str(empty_group_id)]["receiver_count"] == 0

    detail = await api_client.get(f"/api/v1/groups/{group_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["receiver_count"] == 2

    created = await api_client.post("/api/v1/groups", json={"name": "post-group"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["receiver_count"] == 0
