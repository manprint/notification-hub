import uuid

from app.db.session import tenant_session
from app.db.types import ReceiverStatus, Severity
from app.models.group import Group
from app.models.receiver import Receiver
from app.models.severity_rule import SeverityRule


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


async def create_receiver(
    tenant_id: uuid.UUID,
    slug: str,
    group_id: uuid.UUID | None = None,
    name: str = "Test Receiver",
    status: ReceiverStatus = ReceiverStatus.ACTIVE,
    max_body_bytes: int = 1048576,
    rate_limit_per_min: int = 60,
    default_severity: Severity = Severity.INFO,
) -> uuid.UUID:
    """Create a test receiver. Crea anche il group se non ne viene passato uno:
    receivers.group_id ha un FK reale su groups.id, un uuid4 a caso qui
    violerebbe il vincolo."""
    if group_id is None:
        group_id = await create_group(tenant_id, f"Group for {slug}")

    async with tenant_session(tenant_id) as session:
        receiver = Receiver(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            group_id=group_id,
            slug=slug,
            name=name,
            status=status,
            max_body_bytes=max_body_bytes,
            rate_limit_per_min=rate_limit_per_min,
            default_severity=default_severity,
        )
        session.add(receiver)
        await session.flush()
        receiver_id = receiver.id

    return receiver_id


async def create_severity_rule(
    tenant_id: uuid.UUID,
    receiver_id: uuid.UUID,
    pattern: str,
    severity: Severity,
    priority: int = 1,
    case_insensitive: bool = True,
    enabled: bool = True,
) -> uuid.UUID:
    async with tenant_session(tenant_id) as session:
        rule = SeverityRule(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            receiver_id=receiver_id,
            priority=priority,
            pattern=pattern,
            case_insensitive=case_insensitive,
            severity=severity,
            enabled=enabled,
        )
        session.add(rule)
        await session.flush()
        rule_id = rule.id

    return rule_id
