"""E2E per POST /ingest/{slug} (spec 6, 9.1). Ogni test qui fallisce se la
relativa garanzia di comportamento viene rimossa dal codice."""

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.db.session import tenant_session
from app.db.types import ReceiverStatus, Severity
from tests.conftest_factories import create_receiver, create_severity_rule


@pytest.mark.e2e
async def test_ingestion_riuscita_con_regola_di_severity(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    await create_severity_rule(
        tenant_id, receiver_id, pattern="FALL(ITO|IMENT)|ERROR", severity=Severity.ERROR
    )

    response = await api_client.post(f"/ingest/{slug}", content="Backup FALLITO: disco pieno")

    assert response.status_code == 201
    body = response.json()
    assert body["severity"] == "error"
    assert body["severity_source"] == "rule"
    assert body["storage_backend"] == "inline"
    assert uuid.UUID(body["id"])

    async with tenant_session(tenant_id) as session:
        from app.models.notification import Notification

        notification = await session.get(Notification, uuid.UUID(body["id"]))
        assert notification.matched_pattern == "FALL(ITO|IMENT)|ERROR"


@pytest.mark.e2e
async def test_ingestion_usa_default_severity_del_receiver_senza_match(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, default_severity=Severity.WARNING)
    await create_severity_rule(tenant_id, receiver_id, pattern="ERROR", severity=Severity.ERROR)

    response = await api_client.post(f"/ingest/{slug}", content="tutto ok")

    assert response.status_code == 201
    body = response.json()
    assert body["severity"] == "warning"
    assert body["severity_source"] == "receiver_default"


@pytest.mark.e2e
async def test_header_esplicito_vince_sulla_regola(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    await create_severity_rule(tenant_id, receiver_id, pattern="FALLITO", severity=Severity.ERROR)

    response = await api_client.post(
        f"/ingest/{slug}",
        content="Backup FALLITO",
        headers={"X-Severity": "critical"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["severity"] == "critical"
    assert body["severity_source"] == "explicit"


@pytest.mark.e2e
async def test_severity_esplicita_non_valida_scende_alla_regola(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    await create_severity_rule(tenant_id, receiver_id, pattern="FALLITO", severity=Severity.ERROR)

    response = await api_client.post(
        f"/ingest/{slug}",
        content="Backup FALLITO",
        headers={"X-Severity": "banana"},
    )

    assert response.status_code == 201
    assert response.json()["severity_source"] == "rule"


@pytest.mark.e2e
async def test_404_uniforme_slug_inesistente_e_receiver_disabilitato(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, status=ReceiverStatus.DISABLED)

    resp_missing = await api_client.post(f"/ingest/slug-non-esiste-{uuid.uuid4().hex}", content="x")
    resp_disabled = await api_client.post(f"/ingest/{slug}", content="x")

    assert resp_missing.status_code == 404
    assert resp_disabled.status_code == 404
    assert resp_missing.json() == resp_disabled.json()


@pytest.mark.e2e
async def test_404_uniforme_tenant_sospeso(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    resp_missing = await api_client.post(f"/ingest/slug-non-esiste-{uuid.uuid4().hex}", content="x")

    async with tenant_session(tenant_id) as session:
        await session.execute(
            text("UPDATE tenants SET status = 'suspended' WHERE id = :id"), {"id": tenant_id}
        )

    resp_suspended = await api_client.post(f"/ingest/{slug}", content="x")

    assert resp_suspended.status_code == 404
    assert resp_suspended.json() == resp_missing.json()


@pytest.mark.e2e
async def test_idempotenza_su_x_request_id(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    request_id = f"req-{uuid.uuid4().hex}"

    first = await api_client.post(
        f"/ingest/{slug}", content="stesso messaggio", headers={"X-Request-Id": request_id}
    )
    second = await api_client.post(
        f"/ingest/{slug}", content="stesso messaggio", headers={"X-Request-Id": request_id}
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers.get("Idempotent-Replay") == "true"
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.e2e
async def test_idempotenza_concorrente_non_crea_due_notifiche(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    request_id = f"req-concurrent-{uuid.uuid4().hex}"

    first, second = await asyncio.gather(
        api_client.post(
            f"/ingest/{slug}", content="stesso messaggio", headers={"X-Request-Id": request_id}
        ),
        api_client.post(
            f"/ingest/{slug}", content="stesso messaggio", headers={"X-Request-Id": request_id}
        ),
    )

    assert sorted((first.status_code, second.status_code)) == [200, 201]
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.e2e
async def test_senza_x_request_id_ogni_invio_crea_una_notifica_diversa(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    first = await api_client.post(f"/ingest/{slug}", content="stesso messaggio")
    second = await api_client.post(f"/ingest/{slug}", content="stesso messaggio")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.e2e
async def test_body_oltre_max_body_bytes_ritorna_413(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=100)

    response = await api_client.post(f"/ingest/{slug}", content="x" * 200)

    assert response.status_code == 413


@pytest.mark.e2e
async def test_payload_oltre_inline_max_bytes_va_su_object_storage(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=20_971_520)

    large_body = "x" * (1_048_576 + 1)
    response = await api_client.post(f"/ingest/{slug}", content=large_body)

    assert response.status_code == 201
    assert response.json()["storage_backend"] == "object"


@pytest.mark.e2e
async def test_content_type_non_supportato_ritorna_415(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    response = await api_client.post(
        f"/ingest/{slug}",
        content='{"not": "plain text"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 415


@pytest.mark.e2e
async def test_content_type_form_urlencoded_di_curl_e_wget_e_accettato(api_client, two_tenants):
    """curl --data e wget --post-data, i due client citati dalla spec 6.2, impostano
    da soli application/x-www-form-urlencoded quando non lo si specifica: deve
    funzionare esattamente come text/plain, altrimenti nessun esempio della spec
    funzionerebbe davvero."""
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    response = await api_client.post(
        f"/ingest/{slug}",
        content="Backup completato",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 201


@pytest.mark.e2e
async def test_rate_limit_per_slug_ritorna_429(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, rate_limit_per_min=1)

    first = await api_client.post(f"/ingest/{slug}", content="uno")
    second = await api_client.post(f"/ingest/{slug}", content="due")

    assert first.status_code == 201
    assert second.status_code == 429
    assert "retry_after" in second.json()


@pytest.mark.e2e
async def test_contenuto_non_utf8_non_fa_mai_fallire_ingestion(api_client, two_tenants):
    """Invariante I-7: qualunque sequenza di byte viene normalizzata e salvata."""
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    raw = b"prefisso \xff\xfe\x00 suffisso"
    response = await api_client.post(f"/ingest/{slug}", content=raw)

    assert response.status_code == 201
    notification_id = uuid.UUID(response.json()["id"])

    async with tenant_session(tenant_id) as session:
        from app.models.notification import Notification

        result = await session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalar_one()
        assert notification.content_normalized is True
        assert "\x00" not in notification.content
        assert notification.content_size == len(raw)
