import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.db.session import async_session_factory_app, auth_session, ingest_session, tenant_session
from app.models.user import User


@pytest.mark.integration
async def test_lettura_isolata_fra_tenant(two_tenants, make_user):
    tenant_a_id, tenant_b_id = two_tenants
    email_a = f"user-a-{tenant_a_id.hex[:8]}@test.com"
    email_b = f"user-b-{tenant_b_id.hex[:8]}@test.com"

    await make_user(tenant_a_id, email_a)
    await make_user(tenant_b_id, email_b)

    async with tenant_session(tenant_a_id) as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 1
        assert users[0].email == email_a


@pytest.mark.integration
async def test_lettura_senza_guc_non_vede_nulla(two_tenants, make_user):
    """Deny di default (spec 5.1): sul pool app, senza app.tenant_id impostato,
    una tabella scoped-per-tenant come `users` non restituisce nulla, quale che
    sia il tenant_id delle righe presenti.

    Nota: non si puo verificare questo su `receivers` con il pool ingest, come
    faceva la versione precedente di questo test: notifyhub_ingest vede TUTTI i
    receiver di proposito (policy `USING (true)`, spec 5.2), perche deve
    risolvere lo slug senza un contesto di tenant. "Vede zero righe" li non e
    l'invariante giusta da testare — lo e su una tabella davvero scoped."""
    tenant_a_id, _ = two_tenants
    await make_user(tenant_a_id, f"user-guc-{tenant_a_id.hex[:8]}@test.com")

    async with async_session_factory_app() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 0


@pytest.mark.integration
async def test_scrittura_con_tenant_sbagliato_rifiutata(two_tenants, migrated_db):
    tenant_a_id, tenant_b_id = two_tenants

    from app.db.types import UserRole, UserStatus
    from app.models.user import User

    async with tenant_session(tenant_a_id) as session:
        user = User(
            tenant_id=tenant_b_id,
            email="wrong-tenant@test.com",
            password_hash="hash",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)

        with pytest.raises((IntegrityError, ProgrammingError)):
            await session.flush()


@pytest.mark.integration
async def test_update_non_attraversa_i_tenant(two_tenants, make_user):
    tenant_a_id, tenant_b_id = two_tenants

    await make_user(tenant_a_id, f"user-a-{tenant_a_id.hex[:8]}@test.com")
    await make_user(tenant_b_id, f"user-b-{tenant_b_id.hex[:8]}@test.com")

    async with tenant_session(tenant_a_id) as session:
        from app.db.types import UserStatus

        await session.execute(
            text("UPDATE users SET status = :status"),
            {"status": UserStatus.DISABLED},
        )
        await session.flush()

        result = await session.execute(select(User))
        users = result.scalars().all()
        assert users[0].status == UserStatus.DISABLED


@pytest.mark.integration
async def test_ruolo_ingest_legge_solo_receivers():
    from app.models.notification import Notification
    from app.models.receiver import Receiver

    async with ingest_session() as session:
        result = await session.execute(select(Receiver))
        _ = result.scalars().all()

        with pytest.raises((IntegrityError, ProgrammingError)):
            await session.execute(select(Notification))


@pytest.mark.integration
async def test_ruolo_auth_non_puo_scrivere():
    from app.models.user import User

    async with auth_session() as session:
        result = await session.execute(select(User))
        _ = result.scalars().all()

        from app.db.types import UserRole, UserStatus

        user = User(
            tenant_id=uuid.uuid4(),
            email="newuser@test.com",
            password_hash="hash",
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)

        with pytest.raises((IntegrityError, ProgrammingError)):
            await session.flush()


@pytest.mark.integration
async def test_guc_non_persiste_fra_transazioni(two_tenants, make_user):
    """SET LOCAL muore col commit della transazione (spec 5.1): una nuova
    sessione sullo STESSO pool app, senza tenant impostato, non deve vedere le
    righe scritte nella transazione precedente su una connessione riciclata
    dal pool. Va verificato sul pool notifyhub_app, che ha i privilegi per
    leggere users: notifyhub_ingest non li ha per disegno (spec 5.2) e non
    misurerebbe la persistenza della GUC, solo l'assenza del GRANT."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, f"user-a-{tenant_a_id.hex[:8]}@test.com")

    async with async_session_factory_app() as session:
        guc = await session.execute(text("SELECT current_setting('app.tenant_id', true)"))
        assert guc.scalar() in (None, "")

        result = await session.execute(select(User).where(User.tenant_id == tenant_a_id))
        users = result.scalars().all()
        assert len(users) == 0
