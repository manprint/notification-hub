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
from app.db.session import engine_app, tenant_session  # noqa: E402
from app.main import create_app  # noqa: E402


def pytest_configure(config):
    if "ENV_FILE" not in os.environ:
        os.environ["ENV_FILE"] = ".env.test"


def pytest_collection_modifyitems(config, items):
    """Forza loop_scope="session" sui test di tests/integration/.

    Gli engine SQLAlchemy async (app/db/session.py) e il client Redis
    (app/core/redis.py) sono singleton di modulo, come in produzione. I test
    di integrazione condividono quei singleton fra piu funzioni nella stessa
    sessione di pytest: senza questo hook, ogni funzione riceve un event loop
    diverso (default di pytest-asyncio) e il pool asyncpg del secondo test
    che tocca un engine solleva "attached to a different loop".

    Limitato a tests/integration/ e tests/e2e/: sono gli unici che condividono
    i singleton (engine SQLAlchemy, client Redis) fra piu funzioni di test
    nella stessa sessione. Applicarlo anche ai test unitari senza fixture
    asincrone rompe test_redis.py e test_ratelimit.py con "no current event
    loop" — e un limite noto di pytest-asyncio per i test async privi di
    qualunque fixture (pytest-asyncio#596), non risolvibile qui, e questi
    test non hanno comunque bisogno di un loop diverso da quello di default.
    """
    for item in items:
        in_shared_state_suite = "tests/integration/" in str(item.path) or "tests/e2e/" in str(
            item.path
        )
        if in_shared_state_suite and item.get_closest_marker("asyncio"):
            # append=False: deve precedere il marker "asyncio" nudo gia aggiunto
            # dal mode "auto", altrimenti get_closest_marker trova quello senza
            # loop_scope e questo hook non ha alcun effetto.
            item.add_marker(pytest.mark.asyncio(loop_scope="session"), append=False)


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
def migrated_db():
    """Applica `alembic upgrade head` sul database di test reale.

    Deliberatamente NON usa Base.metadata.create_all: quello scavalca le
    migrazioni e produce uno schema senza RLS, senza trigger e senza il CHECK
    di coerenza storage_backend/content, vanificando esattamente le garanzie
    che questa suite deve dimostrare (vedi docs/REVIEW.md, sezione 6).
    """
    from alembic import command
    from alembic.config import Config

    backend_path = os.path.join(os.path.dirname(__file__), "..")
    config = Config(os.path.join(backend_path, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(backend_path, "alembic"))
    command.upgrade(config, "head")
    return True


@pytest.fixture
async def owner_conn(migrated_db):
    async with engine_app.connect() as conn:
        yield conn


@pytest.fixture
async def two_tenants(owner_conn):
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    # slug unique globale (spec 4.1 tenants.slug): con una suite che gira contro
    # un database reale persistente per l'intera sessione, valori letterali fissi
    # collidono al secondo test che richiede questa fixture.
    slug_a = f"tenant-a-{tenant_a_id.hex[:8]}"
    slug_b = f"tenant-b-{tenant_b_id.hex[:8]}"

    await owner_conn.execute(
        text(
            "INSERT INTO tenants (id, name, slug, max_body_bytes, status) "
            "VALUES (:id, :name, :slug, :max_body, :status)"
        ),
        [
            {
                "id": tenant_a_id,
                "name": "Tenant A",
                "slug": slug_a,
                "max_body": 1048576,
                "status": "active",
            },
            {
                "id": tenant_b_id,
                "name": "Tenant B",
                "slug": slug_b,
                "max_body": 1048576,
                "status": "active",
            },
        ],
    )

    await owner_conn.commit()

    return tenant_a_id, tenant_b_id


async def _make_user(
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
def make_user():
    """Espone _make_user come fixture chiamabile: i test fanno
    `await make_user(tenant_id, email)`, quindi il valore della fixture deve
    essere la funzione stessa, non il suo risultato gia atteso."""
    return _make_user


async def _owner_token(api_client, tenant_id: uuid.UUID) -> str:
    """Crea un utente owner nel tenant e ne restituisce l'access token, per i
    test e2e che devono chiamare endpoint protetti da require_admin/require_owner."""
    from app.core.security import hash_password
    from app.db.types import UserRole, UserStatus
    from app.models.user import User

    email = f"owner-{tenant_id.hex[:8]}@test.com"
    async with tenant_session(tenant_id) as session:
        session.add(
            User(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password("correct-horse-battery"),
                role=UserRole.OWNER,
                status=UserStatus.ACTIVE,
            )
        )
    resp = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    return resp.json()["access_token"]


@pytest.fixture
def owner_token():
    """Come make_user: espone _owner_token chiamabile con (api_client, tenant_id)."""
    return _owner_token


@pytest.fixture
async def create_receiver_fixture(two_tenants):
    """Fixture to create test receiver."""
    from tests.conftest_factories import create_receiver

    tenant_a_id, _ = two_tenants

    async def _create_receiver(slug: str, group_id: uuid.UUID | None = None):
        return await create_receiver(tenant_a_id, slug, group_id)

    return _create_receiver


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
    from app.core.security import hash_password

    tenant_a_id, _ = two_tenants
    await _make_user(tenant_a_id, "testuser@test.com", hash_password("test-password-123"))

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@test.com", "password": "test-password-123"},
    )

    # Un login rotto qui deve far fallire ogni test che dipende da questa fixture,
    # non farli passare in silenzio con un token None (vedi docs/REVIEW.md, sez. 6).
    assert (
        response.status_code == 200
    ), f"auth_token fixture: login failed with {response.status_code}: {response.text}"
    return response.json()["access_token"]
