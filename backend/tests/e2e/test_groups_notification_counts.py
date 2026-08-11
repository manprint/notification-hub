"""E2E: notification_count e unread_count nel payload della lista gruppi."""

import uuid

import pytest

from tests.conftest_factories import create_group, create_receiver


@pytest.mark.e2e
async def test_groups_notification_counts_list(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_id = await create_group(tenant_id, "counts-group")
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, group_id=group_id)

    for _ in range(3):
        resp = await api_client.post(f"/ingest/{slug}", content="conta")
        assert resp.status_code == 201, resp.text

    notifications = [
        n["id"]
        for n in (await api_client.get("/api/v1/notifications", headers=headers)).json()[
            "notifications"
        ]
    ]
    patch = await api_client.patch(
        f"/api/v1/notifications/{notifications[0]}", json={"status": "read"}, headers=headers
    )
    assert patch.status_code == 200

    resp = await api_client.get("/api/v1/groups", headers=headers)
    assert resp.status_code == 200, resp.text
    by_id = {g["id"]: g for g in resp.json()}
    group = by_id[str(group_id)]
    assert group["notification_count"] == 3
    assert group["unread_count"] == 2
