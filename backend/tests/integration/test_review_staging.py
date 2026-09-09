"""Integrazione delle regressioni trovate nella revisione pre-staging.

Girano contro Postgres/MinIO reali: sono difetti che si vedono solo con RLS
attiva e con lock veri, cioe esattamente cio che un mock avrebbe nascosto.
Vedi docs/REVIEW.md, sezione "Verifica 3".
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text, update

from app.db.session import async_session_factory_app, tenant_session
from app.db.sync_session import sync_session_factory
from app.db.types import Severity
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.services.quota import enforce_tenant_quotas
from app.services.storage import fetch_object, upload_object
from app.tasks.maintenance import purge_orphan_objects
from tests.conftest_factories import create_receiver


async def _insert_object_notification(
    tenant_id: uuid.UUID, receiver_id: uuid.UUID, storage_key: str
) -> uuid.UUID:
    notification_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            Notification(
                id=notification_id,
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                storage_backend="object",
                content=None,
                storage_key=storage_key,
                content_preview="payload grande",
                content_size=2_097_152,
                content_normalized=False,
                severity=Severity.INFO,
                severity_source="receiver_default",
                status="unread",
                received_at=datetime.now(UTC),
                source_ip=None,
                meta={},
            )
        )
    return notification_id


@pytest.mark.integration
async def test_una_lettura_senza_contesto_di_tenant_non_vede_nessuna_storage_key(two_tenants):
    """Il meccanismo del difetto qui sotto, isolato.

    `notifications` ha FORCE ROW LEVEL SECURITY e il ruolo notifyhub_app non ha
    BYPASSRLS: una SELECT senza `app.tenant_id` impostato non da errore, torna
    zero righe. Un job che legge le chiavi note da una sessione senza contesto
    di tenant crede quindi che non ne esista nessuna.
    """
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    storage_key = f"{tenant_id}/2026/09/09/{uuid.uuid4()}.txt"
    await _insert_object_notification(tenant_id, receiver_id, storage_key)

    with sync_session_factory() as session:
        senza_contesto = session.execute(
            select(Notification.storage_key).where(Notification.storage_key.isnot(None))
        ).scalars()
        assert list(senza_contesto) == []

        session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
        con_contesto = session.execute(
            select(Notification.storage_key).where(
                Notification.tenant_id == tenant_id, Notification.storage_key.isnot(None)
            )
        ).scalars()
        assert storage_key in list(con_contesto)


@pytest.mark.integration
async def test_purge_orphan_objects_non_cancella_i_payload_delle_notifiche_vive(
    two_tenants, monkeypatch
):
    """Il job leggeva `notifications.storage_key` senza contesto di tenant:
    l'insieme delle chiavi note usciva vuoto per costruzione (vedi il test
    sopra) e OGNI oggetto oltre le 24h risultava orfano. Effetto reale: la
    cancellazione da MinIO di tutti i payload offloaded piu vecchi di un
    giorno, con le righe notifications ancora al loro posto e il download
    rotto per sempre."""
    tenant_id, _ = two_tenants
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])

    vivo = f"{tenant_id}/vivo/{uuid.uuid4()}.txt"
    orfano = f"{tenant_id}/orfano/{uuid.uuid4()}.txt"
    await upload_object(vivo, b"payload di una notifica ancora in elenco")
    await upload_object(orfano, b"PUT riuscito con commit fallito")
    await _insert_object_notification(tenant_id, receiver_id, vivo)

    # Oltre la finestra di 24h: entrambi gli oggetti sono candidabili.
    import app.tasks.maintenance as maintenance_module

    adesso = datetime.now(UTC)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return adesso + timedelta(hours=25)

    monkeypatch.setattr(maintenance_module, "datetime", _FakeDateTime)

    purge_orphan_objects()

    # L'orfano vero se ne va...
    with pytest.raises(Exception):  # noqa: B017
        await fetch_object(orfano)
    # ...il payload della notifica viva resta.
    assert await fetch_object(vivo) == b"payload di una notifica ancora in elenco"


async def _riesce_a_bloccare_la_riga_tenant(tenant_id: uuid.UUID) -> bool:
    """`FOR UPDATE NOWAIT` da una seconda transazione: dice se la prima tiene
    un lock sulla riga del tenant senza restare appesa ad aspettarlo."""
    async with async_session_factory_app() as sonda:
        try:
            await sonda.execute(
                text("SELECT id FROM tenants WHERE id = :t FOR UPDATE NOWAIT"), {"t": tenant_id}
            )
            return True
        except Exception:
            return False
        finally:
            await sonda.rollback()


@pytest.mark.integration
async def test_le_quote_illimitate_non_serializzano_l_ingestion(two_tenants):
    """`FOR UPDATE` sulla riga del tenant serializza TUTTE le ingestion di quel
    tenant per la durata della transazione. Veniva preso sempre, anche con
    entrambe le quote a NULL (il default: illimitate), rendendo sequenziale
    l'intera ingestion senza niente da proteggere."""
    tenant_id, _ = two_tenants

    async with tenant_session(tenant_id) as session:
        await enforce_tenant_quotas(session, tenant_id, 1024)
        assert await _riesce_a_bloccare_la_riga_tenant(tenant_id) is True


@pytest.mark.integration
async def test_con_una_quota_configurata_il_lock_resta(two_tenants):
    """L'altra meta dell'invariante: quando c'e una quota da rispettare il lock
    serve, altrimenti due richieste concorrenti la superano entrambe."""
    tenant_id, _ = two_tenants
    async with async_session_factory_app() as session:
        await session.execute(
            update(Tenant).where(Tenant.id == tenant_id).values(max_notifications_per_day=1000)
        )
        await session.commit()

    async with tenant_session(tenant_id) as session:
        await enforce_tenant_quotas(session, tenant_id, 1024)
        assert await _riesce_a_bloccare_la_riga_tenant(tenant_id) is False
