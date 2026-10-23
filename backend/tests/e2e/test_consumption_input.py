"""E2E della consultazione (spec 9.5) sui casi limite dei parametri: byte NUL,
cursori manomessi, date senza fuso, gruppi vuoti e cursore con istanti uguali."""

import base64
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.security import hash_password
from app.db.session import tenant_session
from app.db.types import UserRole, UserStatus
from app.models.notification import Notification
from app.models.user import User
from app.models.user_group_membership import UserGroupMembership
from tests.conftest_factories import create_group, create_receiver

PASSWORD = "correct-horse-battery"  # noqa: S105


async def _member_token(api_client, tenant_id: uuid.UUID, group_id: uuid.UUID) -> str:
    user_id = uuid.uuid4()
    email = f"member-{uuid.uuid4().hex[:8]}@test.com"
    async with tenant_session(tenant_id) as session:
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=UserRole.MEMBER,
                status=UserStatus.ACTIVE,
            )
        )
        session.add(UserGroupMembership(tenant_id=tenant_id, user_id=user_id, group_id=group_id))
    resp = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _cursore(testo: str) -> str:
    return base64.urlsafe_b64encode(testo.encode()).decode()


@pytest.mark.e2e
async def test_q_con_byte_nul_e_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}

    resp = await api_client.get("/api/v1/notifications", params={"q": "a\x00b"}, headers=owner)

    assert resp.status_code == 422


@pytest.mark.e2e
async def test_bulk_read_con_byte_nul_e_422_e_non_segna_nulla(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    await api_client.post(f"/ingest/{slug}", content="resta da leggere")

    resp = await api_client.post(
        "/api/v1/notifications/bulk-read", json={"q": "a\x00b"}, headers=owner
    )

    assert resp.status_code == 422
    lista = await api_client.get("/api/v1/notifications", headers=owner)
    assert lista.json()["unread_count"] == 1


@pytest.mark.e2e
@pytest.mark.parametrize(
    "cursore",
    [
        "%%%",
        _cursore("not-a-date|" + str(uuid.uuid4())),
        _cursore("2026-10-01T00:00:00|non-un-uuid"),
        _cursore("0001-01-01T00:00:00+01:00|" + str(uuid.uuid4())),
    ],
)
async def test_cursore_manomesso_e_422(api_client, two_tenants, owner_token, cursore):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}

    resp = await api_client.get("/api/v1/notifications", params={"cursor": cursore}, headers=owner)

    assert resp.status_code == 422
    assert resp.json()["detail"] == "Invalid cursor."


@pytest.mark.e2e
async def test_from_e_to_senza_fuso_sono_utc_anche_con_tz_locale(
    api_client, two_tenants, owner_token, monkeypatch
):
    """Con TZ=Europe/Rome un `to` senza fuso selezionava due ore prima: la
    notifica appena ricevuta spariva. Un valore senza fuso e' UTC."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    await api_client.post(f"/ingest/{slug}", content="appena arrivata")
    fra_un_ora = datetime.now(UTC) + timedelta(hours=1)

    monkeypatch.setenv("TZ", "Europe/Rome")
    time.tzset()
    try:
        naive = await api_client.get(
            "/api/v1/notifications",
            params={"to": fra_un_ora.replace(tzinfo=None).isoformat()},
            headers=owner,
        )
    finally:
        monkeypatch.undo()
        time.tzset()
    aware = await api_client.get(
        "/api/v1/notifications", params={"to": fra_un_ora.isoformat()}, headers=owner
    )

    assert len(aware.json()["notifications"]) == 1
    assert naive.json()["notifications"] == aware.json()["notifications"]


@pytest.mark.e2e
async def test_member_in_gruppo_vuoto_non_vede_ne_conta_nulla(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    altro_gruppo = await create_group(tenant_id, f"Altro {uuid.uuid4().hex[:6]}")
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, altro_gruppo)
    await api_client.post(f"/ingest/{slug}", content="di un altro gruppo")
    await api_client.post(f"/ingest/{slug}", content="anche questa")
    vuoto = await create_group(tenant_id, f"Vuoto {uuid.uuid4().hex[:6]}")
    member = {"Authorization": f"Bearer {await _member_token(api_client, tenant_id, vuoto)}"}

    lista = await api_client.get("/api/v1/notifications", headers=member)
    riepilogo = await api_client.get("/api/v1/stats/summary", headers=member)
    bulk = await api_client.post("/api/v1/notifications/bulk-read", json={}, headers=member)

    assert lista.json() == {"notifications": [], "next_cursor": None, "unread_count": 0}
    assert riepilogo.json()["total_unread"] == 0
    assert bulk.json() == {"marked_read": 0}
    lista_owner = await api_client.get("/api/v1/notifications", headers=owner)
    assert lista_owner.json()["unread_count"] == 2


@pytest.mark.e2e
async def test_q_di_due_caratteri_cerca_per_sottostringa(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    await api_client.post(f"/ingest/{slug}", content="backup completato")
    await api_client.post(f"/ingest/{slug}", content="disco pieno")

    resp = await api_client.get("/api/v1/notifications", params={"q": "ba"}, headers=owner)

    assert [n["content_preview"] for n in resp.json()["notifications"]] == ["backup completato"]


@pytest.mark.e2e
async def test_cursore_delle_notifiche_con_received_at_uguale(api_client, two_tenants, owner_token):
    """Sette notifiche con lo stesso received_at: il cursore su (received_at, id)
    le deve consegnare tutte, una volta sola."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    for indice in range(7):
        await api_client.post(f"/ingest/{slug}", content=f"messaggio {indice}")
    stesso_istante = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Notification)
            .where(Notification.tenant_id == tenant_id)
            .values(received_at=stesso_istante)
        )

    ids: list[str] = []
    params: dict = {"limit": 3}
    while True:
        pagina = (
            await api_client.get("/api/v1/notifications", params=params, headers=owner)
        ).json()
        ids += [n["id"] for n in pagina["notifications"]]
        if pagina["next_cursor"] is None:
            break
        params = {"limit": 3, "cursor": pagina["next_cursor"]}

    assert len(ids) == 7
    assert len(set(ids)) == 7
