import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.db.session import auth_session, ingest_session, tenant_session
from app.models.user import User


@pytest.mark.integration
@pytest.mark.skip(reason="RLS policies not yet created by migrated_db fixture")
async def test_lettura_isolata_fra_tenant(two_tenants, make_user):
    tenant_a_id, tenant_b_id = two_tenants

    await make_user(tenant_a_id, "user-a@test.com")
    await make_user(tenant_b_id, "user-b@test.com")

    async with tenant_session(tenant_a_id) as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 1
        assert users[0].email == "user-a@test.com"


@pytest.mark.integration
@pytest.mark.skip(reason="RLS policies not yet created by migrated_db fixture")
async def test_lettura_senza_guc_non_vede_nulla():
    async with ingest_session() as session:
        from app.models.receiver import Receiver

        result = await session.execute(select(Receiver))
        receivers = result.scalars().all()
        assert len(receivers) == 0


@pytest.mark.integration
@pytest.mark.skip(reason="RLS policies not yet created by migrated_db fixture")
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

        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.integration
@pytest.mark.skip(reason="RLS policies not yet created by migrated_db fixture")
async def test_update_non_attraversa_i_tenant(two_tenants, make_user):
    tenant_a_id, tenant_b_id = two_tenants

    await make_user(tenant_a_id, "user-a@test.com")
    await make_user(tenant_b_id, "user-b@test.com")

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
@pytest.mark.skip(reason="RLS policies not yet created by migrated_db fixture")
async def test_ruolo_ingest_legge_solo_receivers():
    from app.models.notification import Notification
    from app.models.receiver import Receiver

    async with ingest_session() as session:
        result = await session.execute(select(Receiver))
        _ = result.scalars().all()

        with pytest.raises((IntegrityError, ProgrammingError)):
            await session.execute(select(Notification))


@pytest.mark.integration
@pytest.mark.skip(reason="RLS policies not yet created by migrated_db fixture")
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

        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.integration
@pytest.mark.skip(reason="RLS policies not yet created by migrated_db fixture")
async def test_guc_non_persiste_fra_transazioni(two_tenants, make_user):
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user-a@test.com")

    async with ingest_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 0
