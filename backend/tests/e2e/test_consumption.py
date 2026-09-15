"""E2E per l'API di consultazione (spec 9.5)."""

import uuid

import pytest

from app.db.session import tenant_session
from app.db.types import ReceiverStatus, Severity
from tests.conftest_factories import create_group, create_receiver, create_severity_rule


@pytest.mark.e2e
async def test_lista_esclude_content_completo_e_usa_cursore(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    for i in range(3):
        await api_client.post(f"/ingest/{slug}", content=f"messaggio {i}")

    page1 = await api_client.get("/api/v1/notifications", params={"limit": 2}, headers=headers)
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["notifications"]) == 2
    assert body1["next_cursor"] is not None
    assert "content" not in body1["notifications"][0]

    page2 = await api_client.get(
        "/api/v1/notifications",
        params={"limit": 2, "cursor": body1["next_cursor"]},
        headers=headers,
    )
    assert page2.status_code == 200
    body2 = page2.json()
    ids_page1 = {n["id"] for n in body1["notifications"]}
    ids_page2 = {n["id"] for n in body2["notifications"]}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.mark.e2e
async def test_filtro_severity_min(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    await create_severity_rule(tenant_id, receiver_id, pattern="FALLITO", severity=Severity.ERROR)

    await api_client.post(f"/ingest/{slug}", content="tutto ok")
    await api_client.post(f"/ingest/{slug}", content="Backup FALLITO")

    response = await api_client.get(
        "/api/v1/notifications", params={"severity_min": "error"}, headers=headers
    )
    assert response.status_code == 200
    notifications = response.json()["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["severity"] == "error"


@pytest.mark.e2e
async def test_filtro_ricerca_nel_contenuto(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    await api_client.post(f"/ingest/{slug}", content="disco pieno su var")
    await api_client.post(f"/ingest/{slug}", content="tutto regolare")

    response = await api_client.get("/api/v1/notifications", params={"q": "disco"}, headers=headers)
    assert response.status_code == 200
    notifications = response.json()["notifications"]
    assert len(notifications) == 1
    assert "disco" in notifications[0]["content_preview"]


@pytest.mark.e2e
async def test_download_content_inline(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    ingest_resp = await api_client.post(f"/ingest/{slug}", content="corpo completo")
    notification_id = ingest_resp.json()["id"]

    response = await api_client.get(
        f"/api/v1/notifications/{notification_id}/content", headers=headers
    )
    assert response.status_code == 200
    assert response.text == "corpo completo"


@pytest.mark.e2e
async def test_download_content_object_storage_byte_identico(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=20_971_520)

    large_body = "y" * (1_048_576 + 1)
    ingest_resp = await api_client.post(f"/ingest/{slug}", content=large_body)
    assert ingest_resp.json()["storage_backend"] == "object"
    notification_id = ingest_resp.json()["id"]

    response = await api_client.get(
        f"/api/v1/notifications/{notification_id}/content", headers=headers
    )
    assert response.status_code == 200
    assert response.text == large_body


@pytest.mark.e2e
async def test_patch_segna_letta_e_bulk_read(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    r1 = await api_client.post(f"/ingest/{slug}", content="uno")
    await api_client.post(f"/ingest/{slug}", content="due")
    notification_id = r1.json()["id"]

    patch_resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "read"}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "read"

    bulk_resp = await api_client.post("/api/v1/notifications/bulk-read", json={}, headers=headers)
    assert bulk_resp.status_code == 200
    assert bulk_resp.json()["marked_read"] == 1  # solo quella rimasta unread


@pytest.mark.e2e
async def test_delete_notification_accoda_storage_key_per_oggetti(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=20_971_520)

    large_body = "z" * (1_048_576 + 1)
    ingest_resp = await api_client.post(f"/ingest/{slug}", content=large_body)
    notification_id = ingest_resp.json()["id"]

    from sqlalchemy import select

    from app.models.notification import Notification

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Notification).where(Notification.id == uuid.UUID(notification_id))
        )
        storage_key = result.scalar_one().storage_key

    delete_resp = await api_client.delete(
        f"/api/v1/notifications/{notification_id}", headers=headers
    )
    assert delete_resp.status_code == 204

    from app.models.object_deletion import PendingObjectDeletion

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(PendingObjectDeletion).where(PendingObjectDeletion.storage_key == storage_key)
        )
        assert result.scalar_one_or_none() is not None


@pytest.mark.e2e
async def test_stats_summary(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    await api_client.post(f"/ingest/{slug}", content="uno")
    await api_client.post(f"/ingest/{slug}", content="due")

    response = await api_client.get("/api/v1/stats/summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_unread"] >= 2
    assert "info" in body["by_severity"]
    assert body["notifications_last_24h"] >= 2
    assert body["deliveries_dead"] >= 0
    group_row = next(g for g in body["by_group"] if g["unread_count"] >= 2)
    assert group_row["total"] >= 2


@pytest.mark.e2e
async def test_ricerca_esamina_il_contenuto_oltre_i_4096_caratteri(
    api_client, two_tenants, owner_token
):
    """La ricerca girava su content_preview, cioe' sui primi 4096 caratteri: un
    messaggio lungo era trovabile solo per la sua testa (migrazione 0015)."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    ago = f"ago-{uuid.uuid4().hex[:12]}"
    in_testa = f"testa-{uuid.uuid4().hex[:12]}"
    # L'ago sta ben oltre il taglio della preview, in un corpo che resta inline.
    corpo = f"{in_testa}\n" + ("riempitivo\n" * 1000) + f"{ago}\n"
    assert len(corpo) > 4096
    await api_client.post(f"/ingest/{slug}", content=corpo)
    await api_client.post(f"/ingest/{slug}", content="un altro messaggio qualunque")

    trovate = await api_client.get("/api/v1/notifications", params={"q": ago}, headers=headers)
    assert trovate.status_code == 200
    assert len(trovate.json()["notifications"]) == 1

    # La testa resta cercabile come prima: non e' una sostituzione, e' un'estensione.
    ancora = await api_client.get("/api/v1/notifications", params={"q": in_testa}, headers=headers)
    assert len(ancora.json()["notifications"]) == 1


@pytest.mark.e2e
async def test_ricerca_trova_le_sottostringhe(api_client, two_tenants, owner_token):
    """plainto_tsquery cercava parole intere: 'rror' non trovava 'error'."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    marcatore = uuid.uuid4().hex[:12]
    await api_client.post(f"/ingest/{slug}", content=f"rsync {marcatore}error: file mancante")

    response = await api_client.get(
        "/api/v1/notifications", params={"q": f"{marcatore}err"}, headers=headers
    )
    assert response.status_code == 200
    assert len(response.json()["notifications"]) == 1


@pytest.mark.e2e
async def test_ricerca_tratta_i_metacaratteri_like_come_testo(api_client, two_tenants, owner_token):
    """Chi cerca '50%' vuole le notifiche che contengono '50%', non un jolly."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    marcatore = uuid.uuid4().hex[:12]
    await api_client.post(f"/ingest/{slug}", content=f"{marcatore} disco pieno al 50% del totale")
    await api_client.post(f"/ingest/{slug}", content=f"{marcatore} disco pieno al 5012 blocchi")

    response = await api_client.get(
        "/api/v1/notifications", params={"q": f"{marcatore} disco pieno al 50%"}, headers=headers
    )
    assert response.status_code == 200
    notifications = response.json()["notifications"]
    assert len(notifications) == 1
    assert "50%" in notifications[0]["content_preview"]

    # Stessa storia per l'underscore, jolly di un carattere qualsiasi in LIKE.
    underscore = await api_client.get(
        "/api/v1/notifications", params={"q": "al_50"}, headers=headers
    )
    assert underscore.json()["notifications"] == []


@pytest.mark.e2e
async def test_ricerca_su_payload_offloaded_ricade_sulla_preview(
    api_client, two_tenants, owner_token
):
    """Oltre notifyhub_inline_max_bytes il corpo vive su MinIO e `content` e'
    NULL: Postgres puo' cercare solo nella preview. Il test fissa il limite
    dichiarato nella UI, cosi' che smetta di essere vero senza accorgersene."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=20_971_520)

    in_preview = f"preview-{uuid.uuid4().hex[:12]}"
    oltre = f"oltre-{uuid.uuid4().hex[:12]}"
    corpo = f"{in_preview}\n" + ("z" * 1_048_576) + f"\n{oltre}"
    ingest = await api_client.post(f"/ingest/{slug}", content=corpo)
    assert ingest.status_code == 201

    trovata = await api_client.get(
        "/api/v1/notifications", params={"q": in_preview}, headers=headers
    )
    assert len(trovata.json()["notifications"]) == 1
    assert trovata.json()["notifications"][0]["storage_backend"] == "object"

    non_trovata = await api_client.get(
        "/api/v1/notifications", params={"q": oltre}, headers=headers
    )
    assert non_trovata.json()["notifications"] == []


@pytest.mark.e2e
async def test_filtro_receiver_dentro_il_gruppo(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    group_id = await create_group(tenant_id, f"Gruppo {uuid.uuid4().hex[:8]}")
    slug_a = uuid.uuid4().hex[:22]
    slug_b = uuid.uuid4().hex[:22]
    receiver_a = await create_receiver(tenant_id, slug_a, group_id=group_id, name="Receiver A")
    await create_receiver(tenant_id, slug_b, group_id=group_id, name="Receiver B")

    await api_client.post(f"/ingest/{slug_a}", content="dal receiver A")
    await api_client.post(f"/ingest/{slug_b}", content="dal receiver B")

    tutto_il_gruppo = await api_client.get(
        "/api/v1/notifications", params={"group_id": str(group_id)}, headers=headers
    )
    assert len(tutto_il_gruppo.json()["notifications"]) == 2

    solo_a = await api_client.get(
        "/api/v1/notifications",
        params={"group_id": str(group_id), "receiver_id": str(receiver_a)},
        headers=headers,
    )
    assert solo_a.status_code == 200
    notifications = solo_a.json()["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["receiver_id"] == str(receiver_a)


@pytest.mark.e2e
async def test_bulk_read_rispetta_il_filtro_receiver(api_client, two_tenants, owner_token):
    """'Segna tutte come lette' non deve toccare cio' che il filtro tiene fuori
    dalla vista, receiver compreso."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    group_id = await create_group(tenant_id, f"Gruppo {uuid.uuid4().hex[:8]}")
    slug_a = uuid.uuid4().hex[:22]
    slug_b = uuid.uuid4().hex[:22]
    receiver_a = await create_receiver(tenant_id, slug_a, group_id=group_id, name="Receiver A")
    await create_receiver(tenant_id, slug_b, group_id=group_id, name="Receiver B")

    await api_client.post(f"/ingest/{slug_a}", content="dal receiver A")
    await api_client.post(f"/ingest/{slug_b}", content="dal receiver B")

    bulk = await api_client.post(
        "/api/v1/notifications/bulk-read",
        json={"group_id": str(group_id), "receiver_id": str(receiver_a)},
        headers=headers,
    )
    assert bulk.status_code == 200
    assert bulk.json()["marked_read"] == 1

    rimaste = await api_client.get(
        "/api/v1/notifications",
        params={"group_id": str(group_id), "status": "unread"},
        headers=headers,
    )
    notifications = rimaste.json()["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["receiver_id"] != str(receiver_a)


@pytest.mark.e2e
async def test_stats_summary_dettaglia_i_receiver_del_gruppo(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    group_id = await create_group(tenant_id, f"Gruppo {uuid.uuid4().hex[:8]}")
    slug_attivo = uuid.uuid4().hex[:22]
    receiver_attivo = await create_receiver(
        tenant_id, slug_attivo, group_id=group_id, name="Receiver attivo"
    )
    receiver_muto = await create_receiver(
        tenant_id,
        uuid.uuid4().hex[:22],
        group_id=group_id,
        name="Receiver muto",
        status=ReceiverStatus.DISABLED,
    )

    await api_client.post(f"/ingest/{slug_attivo}", content="uno")
    await api_client.post(f"/ingest/{slug_attivo}", content="due")

    response = await api_client.get("/api/v1/stats/summary", headers=headers)
    assert response.status_code == 200
    group_row = next(g for g in response.json()["by_group"] if g["group_id"] == str(group_id))

    # I quattro campi storici restano dove erano: una SPA vecchia continua a leggerli.
    assert group_row["total"] == 2
    assert group_row["unread_count"] == 2

    per_receiver = {r["receiver_id"]: r for r in group_row["receivers"]}
    assert per_receiver[str(receiver_attivo)]["total"] == 2
    assert per_receiver[str(receiver_attivo)]["unread_count"] == 2
    assert per_receiver[str(receiver_attivo)]["receiver_name"] == "Receiver attivo"
    assert per_receiver[str(receiver_attivo)]["status"] == "active"

    # Un receiver che non ha mai scritto resta in elenco: e' l'informazione che
    # si cerca in un riepilogo, non una riga da nascondere.
    assert per_receiver[str(receiver_muto)]["total"] == 0
    assert per_receiver[str(receiver_muto)]["unread_count"] == 0
    assert per_receiver[str(receiver_muto)]["status"] == "disabled"

    # Il totale del gruppo e' la somma dei suoi receiver.
    assert group_row["total"] == sum(r["total"] for r in group_row["receivers"])
    assert group_row["unread_count"] == sum(r["unread_count"] for r in group_row["receivers"])


@pytest.mark.e2e
async def test_stats_summary_elenca_anche_un_gruppo_senza_receiver(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    group_id = await create_group(tenant_id, f"Gruppo vuoto {uuid.uuid4().hex[:8]}")

    response = await api_client.get("/api/v1/stats/summary", headers=headers)
    group_row = next(g for g in response.json()["by_group"] if g["group_id"] == str(group_id))
    assert group_row["total"] == 0
    assert group_row["unread_count"] == 0
    assert group_row["receivers"] == []
