import asyncio
import uuid
from datetime import datetime

import click

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import async_session_factory_app, engine_app
from app.db.types import TenantStatus, UserRole, UserStatus
from app.models.tenant import Tenant
from app.models.user import User


@click.group()
def cli() -> None:
    """NotifyHub CLI."""
    pass


@cli.command()
@click.option(
    "--tenant-name",
    prompt="Tenant name",
    help="Name of the tenant to create",
)
@click.option(
    "--owner-email",
    prompt="Owner email",
    help="Email of the tenant owner",
)
@click.option(
    "--owner-password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Password for the owner",
)
def bootstrap(tenant_name: str, owner_email: str, owner_password: str) -> None:
    """Bootstrap a new tenant with owner user."""
    asyncio.run(_bootstrap(tenant_name, owner_email, owner_password))


async def _bootstrap(tenant_name: str, owner_email: str, owner_password: str) -> None:
    async with engine_app.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory_app() as session:
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        tenant = Tenant(
            id=tenant_id,
            name=tenant_name,
            status=TenantStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(tenant)

        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email=owner_email,
            password_hash=hash_password(owner_password),
            role=UserRole.OWNER,
            status=UserStatus.ACTIVE,
            last_login_at=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(user)

        await session.commit()

        click.echo(f"✓ Tenant created: {tenant_name} (ID: {tenant_id})")
        click.echo(f"✓ Owner created: {owner_email} (ID: {user_id})")


if __name__ == "__main__":
    cli()
