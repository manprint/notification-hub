"""Elenco utenti: ordine stabile fra una richiesta e l'altra (spec 9.2)."""

import uuid

import pytest


@pytest.mark.e2e
async def test_elenco_utenti_ha_un_ordine_stabile_per_email(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    admin = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    tag = uuid.uuid4().hex[:6]
    # Inserimento in ordine non alfabetico: senza ORDER BY la tabella ricalca
    # l'ordine fisico delle righe, che cambia a ogni UPDATE.
    for lettera in ["d", "b", "c", "a"]:
        resp = await api_client.post(
            "/api/v1/users",
            json={"email": f"{lettera}-{tag}@test.com", "password": "x" * 12, "role": "member"},
            headers=admin,
        )
        assert resp.status_code == 201

    primo = await api_client.get("/api/v1/users", headers=admin)
    secondo = await api_client.get("/api/v1/users", headers=admin)
    emails = [u["email"] for u in primo.json()]
    assert emails == sorted(emails)
    assert [u["email"] for u in secondo.json()] == emails
