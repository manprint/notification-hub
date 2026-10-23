"""E2E: chi puo vedere l'elenco dei DeliveryChannel (spec 9.4, matrice ruoli).

La riga "Vedere l'elenco dei DeliveryChannel (URL mascherato)" e' consentita a
owner, admin e member, e negata al viewer. Il viewer consulta /deliveries, non
i canali: l'hint del webhook e l'ultimo errore del canale restano fuori dalla sua
portata.
"""

import uuid

import pytest
from sqlalchemy import update

from app.core.security import hash_password
from app.db.session import tenant_session
from app.db.types import UserRole
from app.models.user import User

WEBHOOK = "https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXXXXXXXXXX"


async def _token_di_ruolo(api_client, tenant_id, make_user, ruolo: UserRole) -> dict:
    email = f"{ruolo.value}-{uuid.uuid4().hex[:8]}@acme-notifyhub.com"
    password = "ruolo-password-123"
    await make_user(tenant_id, email, hash_password(password))
    async with tenant_session(tenant_id) as session:
        await session.execute(update(User).where(User.email == email).values(role=ruolo))
    login = await api_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.e2e
async def test_viewer_non_legge_i_canali_ma_member_si(
    api_client, two_tenants, make_user, owner_token
):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}

    creato = await api_client.post(
        "/api/v1/channels",
        json={"name": f"Slack {uuid.uuid4().hex[:6]}", "type": "slack", "webhook_url": WEBHOOK},
        headers=owner,
    )
    assert creato.status_code == 201, creato.text
    channel_id = creato.json()["id"]

    viewer = await _token_di_ruolo(api_client, tenant_id, make_user, UserRole.VIEWER)
    assert (await api_client.get("/api/v1/channels", headers=viewer)).status_code == 403
    assert (await api_client.get(f"/api/v1/channels/{channel_id}", headers=viewer)).status_code == 403

    member = await _token_di_ruolo(api_client, tenant_id, make_user, UserRole.MEMBER)
    elenco = await api_client.get("/api/v1/channels", headers=member)
    assert elenco.status_code == 200, elenco.text
    assert channel_id in [canale["id"] for canale in elenco.json()]
    dettaglio = await api_client.get(f"/api/v1/channels/{channel_id}", headers=member)
    assert dettaglio.status_code == 200, dettaglio.text
