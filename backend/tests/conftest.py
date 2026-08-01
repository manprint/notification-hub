import os
import uuid

import httpx
import pytest
from dotenv import load_dotenv
from sqlalchemy import text

backend_dir = os.path.join(os.path.dirname(__file__), "..")
env_file = os.path.join(backend_dir, os.environ.get("ENV_FILE", ".env.test"))
load_dotenv(env_file)

import app.models  # noqa: F401, E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine_app, tenant_session  # noqa: E402
from app.main import create_app  # noqa: E402


def pytest_configure(config):
    if "ENV_FILE" not in os.environ:
        os.environ["ENV_FILE"] = ".env.test"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def api_client():
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def migrated_db():
    async with engine_app.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return True


@pytest.fixture
async def owner_conn(migrated_db):
    async with engine_app.connect() as conn:
        yield conn


@pytest.fixture
async def two_tenants(owner_conn):
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    await owner_conn.execute(
        text(
            "INSERT INTO tenants (id, name, slug, max_body_bytes, status) "
            "VALUES (:id, :name, :slug, :max_body, :status)"
        ),
        [
            {
                "id": tenant_a_id,
                "name": "Tenant A",
                "slug": "tenant-a",
                "max_body": 1048576,
                "status": "active",
            },
            {
                "id": tenant_b_id,
                "name": "Tenant B",
                "slug": "tenant-b",
                "max_body": 1048576,
                "status": "active",
            },
        ],
    )

    await owner_conn.commit()

    return tenant_a_id, tenant_b_id


async def make_user(
    tenant_id: uuid.UUID,
    email: str,
    password_hash: str = "hash",  # noqa: S107
):
    async with tenant_session(tenant_id) as session:
        from app.db.types import UserRole, UserStatus
        from app.models.user import User

        user = User(
            tenant_id=tenant_id,
            email=email,
            password_hash=password_hash,
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.flush()
        return user


@pytest.fixture
async def create_receiver_fixture(two_tenants):
    """Fixture to create test receiver."""
    from tests.conftest_factories import create_receiver

    tenant_a_id, _ = two_tenants

    async def _create_receiver(slug: str, group_id: uuid.UUID | None = None):
        return await create_receiver(tenant_a_id, slug, group_id)

    return _create_receiver


@pytest.fixture
async def create_api_key_fixture(two_tenants):
    """Fixture to create test API key."""
    from tests.conftest_factories import create_api_key

    tenant_a_id, _ = two_tenants

    async def _create_api_key(receiver_id: uuid.UUID, label: str = "Test Key"):
        return await create_api_key(tenant_a_id, receiver_id, label)

    return _create_api_key


@pytest.fixture
async def create_group_fixture(two_tenants):
    """Fixture to create test group."""
    from tests.conftest_factories import create_group

    tenant_a_id, _ = two_tenants

    async def _create_group(name: str = "Test Group", description: str | None = None):
        return await create_group(tenant_a_id, name, description)

    return _create_group


@pytest.fixture
async def auth_token(api_client, two_tenants):
    """Fixture to get auth token for test user."""
    tenant_a_id, _ = two_tenants
    await make_user(tenant_a_id, "testuser@test.com")

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@test.com", "password": "test"},
    )

    if response.status_code == 200:
        return response.json()["access_token"]
    return None
