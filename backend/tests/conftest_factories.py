import uuid

from app.db.session import tenant_session
from app.models.api_key import ApiKey
from app.models.group import Group
from app.models.receiver import Receiver


async def create_receiver(
    tenant_id: uuid.UUID, slug: str, group_id: uuid.UUID | None = None
) -> Receiver:
    """Create a test receiver."""
    if group_id is None:
        group_id = uuid.uuid4()

    async with tenant_session(tenant_id) as session:
        receiver = Receiver(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            group_id=group_id,
            slug=slug,
        )
        session.add(receiver)
        await session.flush()
        receiver_id = receiver.id

    return receiver_id


async def create_api_key(
    tenant_id: uuid.UUID, receiver_id: uuid.UUID, label: str = "Test Key"
) -> tuple[uuid.UUID, str]:
    """Create test API key and return (id, plaintext_key)."""
    import secrets

    plaintext_key = secrets.token_urlsafe(32)
    from app.core.security import hash_token

    key_hash = hash_token(plaintext_key)

    async with tenant_session(tenant_id) as session:
        api_key = ApiKey(
            id=uuid.uuid4(),
            receiver_id=receiver_id,
            key_hash=key_hash,
            label=label,
        )
        session.add(api_key)
        await session.flush()
        api_key_id = api_key.id

    return api_key_id, plaintext_key


async def create_group(
    tenant_id: uuid.UUID,
    name: str = "Test Group",
    description: str | None = None,
) -> uuid.UUID:
    """Create test group."""
    async with tenant_session(tenant_id) as session:
        group = Group(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            description=description,
        )
        session.add(group)
        await session.flush()
        group_id = group.id

    return group_id
