"""E2E: input fuori range non deve produrre 500 (spec 6.2, 9.1, invariante I-7)."""

import uuid

import pytest
from sqlalchemy import select

from app.db.session import tenant_session
from app.models.notification import Notification
from app.models.severity_rule import SeverityRule
from tests.conftest_factories import create_receiver


@pytest.mark.e2e
async def test_exit_code_fuori_dall_intero_a_32_bit_viene_ignorato_con_201(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    response = await api_client.post(
        f"/ingest/{slug}", content="wrapper", headers={"X-Exit-Code": "2147483648"}
    )

    assert response.status_code == 201
    async with tenant_session(tenant_id) as session:
        notification = await session.get(Notification, uuid.UUID(response.json()["id"]))
        assert notification.exit_code is None


@pytest.mark.e2e
async def test_duration_ms_oltre_il_bigint_viene_ignorata_con_201(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    response = await api_client.post(
        f"/ingest/{slug}",
        content="wrapper",
        headers={"X-Duration-Ms": "9223372036854775808"},
    )

    assert response.status_code == 201
    async with tenant_session(tenant_id) as session:
        notification = await session.get(Notification, uuid.UUID(response.json()["id"]))
        assert notification.duration_ms is None


@pytest.mark.e2e
async def test_severity_rule_con_byte_nul_nel_pattern_ritorna_422(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_resp = await api_client.post(
        "/api/v1/groups", json={"name": f"Group {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    receiver_resp = await api_client.post(
        f"/api/v1/groups/{group_resp.json()['id']}/receivers", json={"name": "R"}, headers=headers
    )
    receiver_id = receiver_resp.json()["id"]

    response = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/severity-rules",
        json={"priority": 1, "pattern": "a\x00b", "severity": "error"},
        headers=headers,
    )

    assert response.status_code == 422
    async with tenant_session(tenant_id) as session:
        rules = await session.execute(
            select(SeverityRule.id).where(SeverityRule.receiver_id == uuid.UUID(receiver_id))
        )
        assert rules.all() == []
