"""Domini di rete privata come nome utente, dall'API alla CLI.

Riproduce il difetto chiuso: un owner creato con `admin@...local` non riusciva ad
autenticarsi, perche' `bootstrap` accettava l'indirizzo e il login lo rifiutava.
"""

import uuid

import pytest
from click.testing import CliRunner

from app.cli import bootstrap
from app.core.security import hash_password
from app.db.session import tenant_session
from app.db.types import UserRole, UserStatus
from app.models.user import User


async def _crea_owner(tenant_id: uuid.UUID, email: str, password: str) -> None:
    async with tenant_session(tenant_id) as session:
        session.add(
            User(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(password),
                role=UserRole.OWNER,
                status=UserStatus.ACTIVE,
            )
        )


@pytest.mark.e2e
@pytest.mark.parametrize("tld", ["local", "test"])
async def test_login_con_dominio_interno(api_client, two_tenants, tld):
    tenant_id, _ = two_tenants
    email = f"owner-{uuid.uuid4().hex[:8]}@notifyhub.{tld}"
    await _crea_owner(tenant_id, email, "correct-horse-battery")

    resp = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    # Prima della correzione: 422 da email-validator, e l'owner era inutilizzabile.
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


@pytest.mark.e2e
async def test_invito_a_un_dominio_interno(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)

    resp = await api_client.post(
        "/api/v1/invitations",
        json={"email": f"collega-{uuid.uuid4().hex[:6]}@sede.local", "role": "member"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


@pytest.mark.e2e
async def test_login_con_email_malformata_resta_422(api_client, two_tenants):
    """L'allineamento allarga i domini ammessi, non spegne la validazione."""
    tenant_id, _ = two_tenants
    resp = await api_client.post(
        "/api/v1/auth/login", json={"email": "admin@@notifyhub.local", "password": "x"}
    )
    assert resp.status_code == 422


@pytest.mark.e2e
def test_bootstrap_rifiuta_una_email_malformata():
    """La CLI valida prima di scrivere: senza, il difetto si sposterebbe da
    `.local` a un indirizzo storto, con lo stesso esito (owner inutilizzabile)."""
    esito = CliRunner().invoke(
        bootstrap,
        ["--tenant-name", "ACME", "--email", "admin@@notifyhub.local", "--password", "x" * 12],
    )
    assert esito.exit_code != 0
    assert "--email" in esito.output
