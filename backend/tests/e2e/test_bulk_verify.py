"""E2E di POST /notifications/bulk-verify e del conteggio non verificate nel riepilogo."""

import uuid

import pytest
from sqlalchemy import select

from app.db.session import tenant_session
from app.models.audit_event import AuditEvent
from tests.conftest_factories import create_group, create_receiver
from tests.e2e.test_consumption_input import _member_token


async def _setup(api_client, tenant_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    group_id = await create_group(tenant_id, f"Gruppo {uuid.uuid4().hex[:8]}")
    slug_a = uuid.uuid4().hex[:22]
    slug_b = uuid.uuid4().hex[:22]
    receiver_a = await create_receiver(tenant_id, slug_a, group_id=group_id, name="A")
    receiver_b = await create_receiver(tenant_id, slug_b, group_id=group_id, name="B")
    for _ in range(2):
        await api_client.post(f"/ingest/{slug_a}", content="dal receiver A")
    await api_client.post(f"/ingest/{slug_b}", content="dal receiver B")
    return group_id, receiver_a, receiver_b


@pytest.mark.e2e
async def test_bulk_verify_rispetta_filtri_e_scrive_audit(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id, receiver_a, _ = await _setup(api_client, tenant_id)

    resp = await api_client.post(
        "/api/v1/notifications/bulk-verify",
        json={"group_id": str(group_id), "receiver_id": str(receiver_a), "mark_verified": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"updated": 2}

    lista = await api_client.get(
        "/api/v1/notifications", params={"group_id": str(group_id)}, headers=headers
    )
    per_receiver = {
        (n["receiver_id"], n["verified"], n["verified_by_email"] is not None)
        for n in lista.json()["notifications"]
    }
    assert (str(receiver_a), True, True) in per_receiver
    assert all(not v for r, v, _ in per_receiver if r != str(receiver_a))

    # Ripetere non tocca nulla: le righe gia' verificate restano com'erano.
    again = await api_client.post(
        "/api/v1/notifications/bulk-verify",
        json={"group_id": str(group_id), "receiver_id": str(receiver_a), "mark_verified": True},
        headers=headers,
    )
    assert again.json() == {"updated": 0}

    stats = await api_client.get("/api/v1/stats/summary", headers=headers)
    group_row = next(g for g in stats.json()["by_group"] if g["group_id"] == str(group_id))
    assert group_row["unverified_count"] == 1
    receivers = {r["receiver_id"]: r for r in group_row["receivers"]}
    assert receivers[str(receiver_a)]["unverified_count"] == 0

    undo = await api_client.post(
        "/api/v1/notifications/bulk-verify",
        json={"group_id": str(group_id), "mark_verified": False},
        headers=headers,
    )
    assert undo.json() == {"updated": 2}
    lista = await api_client.get(
        "/api/v1/notifications", params={"group_id": str(group_id)}, headers=headers
    )
    assert all(
        not n["verified"] and n["verified_by_email"] is None for n in lista.json()["notifications"]
    )

    async with tenant_session(tenant_id) as session:
        actions = (
            await session.execute(
                select(AuditEvent.action, AuditEvent.context).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.action.like("notification.bulk_marked_%verified"),
                )
            )
        ).all()
    by_action = {action: context for action, context in actions}
    assert by_action["notification.bulk_marked_verified"]["count"] == 2
    assert by_action["notification.bulk_marked_unverified"]["count"] == 2


@pytest.mark.e2e
async def test_bulk_verify_riservato_ad_admin(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    group_id, _, _ = await _setup(api_client, tenant_id)
    member = {"Authorization": f"Bearer {await _member_token(api_client, tenant_id, group_id)}"}

    resp = await api_client.post(
        "/api/v1/notifications/bulk-verify",
        json={"group_id": str(group_id), "mark_verified": True},
        headers=member,
    )
    assert resp.status_code == 403


@pytest.mark.e2e
async def test_bulk_verify_richiede_mark_verified(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    resp = await api_client.post("/api/v1/notifications/bulk-verify", json={}, headers=headers)
    assert resp.status_code == 422
