import asyncio
import uuid

import click

from app.core.security import hash_password
from app.db.session import async_session_factory_app, tenant_session
from app.db.types import TenantStatus, UserRole, UserStatus
from app.models.tenant import Tenant
from app.models.user import User
from app.services.severity_presets import sync_builtin_presets


@click.group()
def cli() -> None:
    """NotifyHub CLI."""


@cli.command()
@click.option("--tenant-name", prompt="Tenant name", help="Name of the tenant to create")
@click.option("--email", prompt="Owner email", help="Email of the tenant owner")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Password for the owner",
)
def bootstrap(tenant_name: str, email: str, password: str) -> None:
    """Bootstrap a new tenant with its first owner user.

    Presuppone che `alembic upgrade head` sia gia stato eseguito: questo comando
    non crea schema, solo dati. Va lanciato con `ALLOW_PUBLIC_REGISTRATION=false`
    per creare il primo tenant di un'istanza self-hosted (spec 10.2).
    """
    asyncio.run(_bootstrap(tenant_name, email, password))


async def _bootstrap(tenant_name: str, email: str, password: str) -> None:
    tenant_id = uuid.uuid4()

    # tenants non ha RLS (spec 4): l'insert avviene sulla sessione app "nuda",
    # senza app.tenant_id impostato.
    async with async_session_factory_app() as session:
        tenant = Tenant(
            id=tenant_id,
            name=tenant_name,
            slug=tenant_name.lower().replace(" ", "-"),
            status=TenantStatus.ACTIVE,
        )
        session.add(tenant)
        await session.commit()

    # users ha RLS: l'insert deve avvenire con app.tenant_id impostato sul tenant
    # appena creato, altrimenti la policy WITH CHECK lo rifiuta (I-1).
    user_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.OWNER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)

    # Un tenant nuovo nasce con i preset predefiniti gia installati: senza,
    # il primo receiver partirebbe con zero regole e la sezione Preset vuota.
    async with tenant_session(tenant_id) as session:
        installed = await sync_builtin_presets(session, tenant_id)

    click.echo(f"Tenant created: {tenant_name} (ID: {tenant_id})")
    click.echo(f"Owner created: {email} (ID: {user_id})")
    click.echo(f"Severity presets installed: {', '.join(installed) if installed else 'none'}")


@cli.command("sync-presets")
def sync_presets() -> None:
    """Installa in ogni tenant i preset predefiniti che gli mancano.

    Da eseguire dopo un aggiornamento che aggiunge preset al catalogo. Non tocca
    le copie gia presenti, nemmeno se sono state modificate: e additiva e si puo
    ripetere senza conseguenze.
    """
    asyncio.run(_sync_presets())


async def _sync_presets() -> None:
    from sqlalchemy import select

    async with async_session_factory_app() as session:
        result = await session.execute(select(Tenant.id, Tenant.name).order_by(Tenant.name))
        tenants = result.all()

    for tenant_id, tenant_name in tenants:
        async with tenant_session(tenant_id) as session:
            installed = await sync_builtin_presets(session, tenant_id)
        if installed:
            click.echo(f"{tenant_name}: installed {', '.join(installed)}")
        else:
            click.echo(f"{tenant_name}: already up to date")


if __name__ == "__main__":
    cli()
