import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import client_ip, current_claims, db, require_admin
from app.core.config import get_settings
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import (
    AccessClaims,
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.core.urls import public_base_url
from app.db.session import tenant_session
from app.db.types import TenantStatus, UserRole, UserStatus
from app.models.invitation import Invitation
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    InvitationAcceptIn,
    InvitationIn,
    InvitationOut,
    InvitationSummaryOut,
    LoginIn,
    LogoutIn,
    MeOut,
    RefreshIn,
    RegisterIn,
    TokenPairOut,
)
from app.services.identity import find_invitation, find_refresh_token, find_user_by_email
from app.services.ratelimit import sliding_window_hit

router = APIRouter(prefix="/auth", tags=["auth"])
# Le rotte inviti sono sotto /api/v1/invitations, non /api/v1/auth/invitations
# (spec 9.2: la tabella le elenca nella sezione Auth ma il path e a livello
# radice, come /api/v1/users).
invitations_router = APIRouter(prefix="/invitations", tags=["auth"])


@router.post("/register", status_code=201)
async def register(body: RegisterIn) -> dict:
    """Crea Tenant + primo utente owner. Disabilitato di default (spec 10.2):
    un'istanza self-hosted esposta su internet con registrazione aperta si
    riempie di tenant spazzatura."""
    settings = get_settings()
    if not settings.allow_public_registration:
        raise Problem(
            status=403,
            type=PROBLEM_TYPES["forbidden"],
            title="Forbidden",
            detail="Public registration is disabled. Use the bootstrap CLI.",
        )

    existing = await find_user_by_email(body.email)
    if existing is not None:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="Email already registered.",
        )

    from app.db.session import async_session_factory_app

    tenant_id = uuid.uuid4()
    async with async_session_factory_app() as session:
        tenant = Tenant(
            id=tenant_id,
            name=body.tenant_name,
            slug=f"{body.tenant_name.lower().replace(' ', '-')}-{tenant_id.hex[:8]}",
            status=TenantStatus.ACTIVE,
        )
        session.add(tenant)
        await session.commit()

    password_hash = await asyncio.to_thread(hash_password, body.password)
    user_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email=body.email,
            password_hash=password_hash,
            role=UserRole.OWNER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)

    # Come nel bootstrap da CLI: un tenant nuovo trova i preset predefiniti gia
    # installati e modificabili, invece di una sezione Preset vuota.
    from app.services.severity_presets import sync_builtin_presets

    async with tenant_session(tenant_id) as session:
        await sync_builtin_presets(session, tenant_id)

    return {"tenant_id": str(tenant_id), "user_id": str(user_id)}


@router.post("/login", response_model=TokenPairOut, status_code=200)
async def login(body: LoginIn, request: Request) -> TokenPairOut:
    # Chiave su (email, IP): sulla sola email chiunque conosca un indirizzo
    # potrebbe bloccare quell'account inviando richieste false (spec 10.2
    # chiede esplicitamente (email, IP)).
    #
    # L'IP va risolto con la stessa regola dell'ingestion (api/deps.client_ip):
    # dietro nginx `request.client.host` e l'indirizzo del proxy per TUTTI, la
    # chiave si riduce di fatto alla sola email ed e' di nuovo possibile bloccare
    # un account noto con dieci tentativi sbagliati — esattamente cio' che questa
    # chiave composta doveva impedire.
    rate_limit_key = f"login_attempts:{body.email}:{client_ip(request)}"
    rate_limit = await sliding_window_hit(rate_limit_key, 10, 900)

    if not rate_limit.allowed:
        raise Problem(
            status=429,
            type=PROBLEM_TYPES["rate_limited"],
            title="Too Many Requests",
            detail="Too many login attempts. Please try again later.",
            extra={"retry_after": rate_limit.retry_after},
        )

    user_identity = await find_user_by_email(body.email)

    password_matches = bool(
        user_identity
        and await asyncio.to_thread(verify_password, body.password, user_identity.password_hash)
    )
    if not password_matches or user_identity is None:
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid credentials.",
        )

    if user_identity.status != "active":
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid credentials.",
        )

    tenant_id = uuid.UUID(user_identity.tenant_id)
    async with tenant_session(tenant_id) as session:
        tenant_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = tenant_result.scalar_one()

        if tenant.status != "active":
            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="Invalid credentials.",
            )

        user_result = await session.execute(
            select(User).where(User.id == uuid.UUID(user_identity.id))
        )
        user = user_result.scalar_one()
        user.last_login_at = datetime.now(UTC)

        settings = get_settings()
        refresh_plain, refresh_hash = new_refresh_token()
        # Una famiglia nuova per ogni login: sessioni su dispositivi diversi
        # non condividono la stessa famiglia, cosi il riuso rilevato su una
        # non revoca le altre (spec 4.1, contrariamente al bug descritto in
        # docs/REVIEW.md S4, dove family_id coincideva con lo user_id).
        family_id = uuid.uuid4()

        refresh_token_row = RefreshToken(
            tenant_id=tenant_id,
            user_id=user.id,
            token_hash=refresh_hash,
            jti=str(uuid.uuid4()),
            family_id=family_id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            revoked_at=None,
            user_agent=None,
            ip=None,
        )
        session.add(refresh_token_row)
        await session.flush()

        access_token, expires_in = create_access_token(str(user.id), str(tenant_id), user.role)

    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_plain,
        token_type="bearer",  # noqa: S106
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenPairOut, status_code=200)
async def refresh(body: RefreshIn) -> TokenPairOut:
    refresh_token_identity = await find_refresh_token(hash_token(body.refresh_token))

    if not refresh_token_identity:
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid refresh token.",
        )

    tenant_id = uuid.UUID(refresh_token_identity.tenant_id)
    async with tenant_session(tenant_id) as session:
        refresh_result = await session.execute(
            select(RefreshToken)
            .where(RefreshToken.id == uuid.UUID(refresh_token_identity.id))
            .with_for_update()
        )
        refresh_token_row = refresh_result.scalar_one_or_none()

        if refresh_token_row is None or refresh_token_row.revoked_at is not None:
            # Riuso di un token gia ruotato: revoca l'intera famiglia (spec 4.1).
            if refresh_token_row is not None and refresh_token_row.family_id:
                refresh_result = await session.execute(
                    select(RefreshToken).where(
                        RefreshToken.family_id == refresh_token_row.family_id
                    )
                )
                family_tokens = refresh_result.scalars().all()
                for token in family_tokens:
                    token.revoked_at = datetime.now(UTC)
                # tenant_session fa rollback quando un'eccezione esce dal
                # blocco: senza un commit esplicito qui, la revoca della
                # famiglia scritta sopra sparirebbe insieme al raise sotto,
                # lasciando il resto della famiglia ancora valido.
                await session.commit()

            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="Refresh token revoked or invalid.",
            )

        if refresh_token_row.expires_at < datetime.now(UTC):
            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="Refresh token expired.",
            )

        user_result = await session.execute(
            select(User).where(User.id == uuid.UUID(refresh_token_identity.user_id))
        )
        user = user_result.scalar_one()

        tenant_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = tenant_result.scalar_one()

        if user.status != "active" or tenant.status != "active":
            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="User or tenant inactive.",
            )

        settings = get_settings()
        old_family_id = refresh_token_row.family_id
        refresh_token_row.revoked_at = datetime.now(UTC)

        refresh_plain, refresh_hash = new_refresh_token()
        new_refresh_token_row = RefreshToken(
            tenant_id=tenant_id,
            user_id=user.id,
            token_hash=refresh_hash,
            jti=str(uuid.uuid4()),
            family_id=old_family_id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            revoked_at=None,
            user_agent=None,
            ip=None,
        )
        session.add(new_refresh_token_row)
        await session.flush()

        access_token, expires_in = create_access_token(str(user.id), str(tenant_id), user.role)

    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_plain,
        token_type="bearer",  # noqa: S106
        expires_in=expires_in,
    )


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutIn,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    if body.revoke_all:
        refresh_result = await session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == uuid.UUID(claims.sub),
                RefreshToken.tenant_id == uuid.UUID(claims.tid),
                RefreshToken.revoked_at.is_(None),
            )
        )
        tokens = refresh_result.scalars().all()
        for token in tokens:
            token.revoked_at = datetime.now(UTC)
    else:
        refresh_result = await session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == uuid.UUID(claims.sub),
                RefreshToken.tenant_id == uuid.UUID(claims.tid),
                RefreshToken.jti == body.jti,
            )
        )
        refresh_row: RefreshToken | None = refresh_result.scalar_one_or_none()
        if refresh_row is not None:
            refresh_row.revoked_at = datetime.now(UTC)

    await session.flush()


@router.get("/me", response_model=MeOut)
async def me(  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> MeOut:
    user_result = await session.execute(select(User).where(User.id == uuid.UUID(claims.sub)))
    user = user_result.scalar_one()

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == uuid.UUID(claims.tid)))
    tenant = tenant_result.scalar_one()

    return MeOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
    )


async def _send_invitation_email(email: str, invite_url: str) -> bool:
    settings = get_settings()
    if not settings.smtp_enabled or settings.smtp_host is None:
        return False

    import smtplib
    from email.message import EmailMessage

    message = EmailMessage()
    message["Subject"] = "Invito a NotifyHub"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(f"Sei stato invitato a NotifyHub. Accetta l'invito: {invite_url}")

    smtp_host: str = settings.smtp_host

    def _send() -> bool:
        try:
            with smtplib.SMTP(smtp_host, settings.smtp_port or 587, timeout=10) as smtp:
                if settings.smtp_user and settings.smtp_password:
                    smtp.starttls()
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
            return True
        except OSError:
            return False

    # smtplib e' sincrono e puo restare bloccato fino al timeout: non deve
    # fermare l'event loop dell'API e tutte le richieste concorrenti.
    return await asyncio.to_thread(_send)


@invitations_router.post("", response_model=InvitationOut, status_code=201)
async def create_invitation(
    body: InvitationIn,
    request: Request,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> InvitationOut:
    if body.role == UserRole.OWNER and claims.role != UserRole.OWNER:
        raise Problem(
            status=403,
            type=PROBLEM_TYPES["forbidden"],
            title="Forbidden",
            detail="Only an owner can grant the owner role.",
        )

    existing = await find_user_by_email(body.email)
    if existing is not None:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="Email already registered.",
        )

    token_plain, token_hash = new_refresh_token()

    invitation = Invitation(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID(claims.tid),
        email=body.email,
        role=body.role,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        accepted_at=None,
        invited_by=uuid.UUID(claims.sub),
    )
    session.add(invitation)
    await session.flush()

    # Il token viaggia solo nel frammento dell'URL (mai trasmesso al server) e
    # la SPA lo gira nel body della POST di /invitations/accept (spec 9.2).
    invite_url = f"{public_base_url(request)}/invite#token={token_plain}"
    email_sent = await _send_invitation_email(body.email, invite_url)

    return InvitationOut(
        id=str(invitation.id),
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        invite_url=invite_url,
        email_sent=email_sent,
    )


@invitations_router.get("", response_model=list[InvitationSummaryOut])
async def list_invitations(
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[InvitationSummaryOut]:
    result = await session.execute(
        select(Invitation)
        .where(
            Invitation.tenant_id == uuid.UUID(claims.tid),
            Invitation.accepted_at.is_(None),
        )
        .order_by(Invitation.expires_at.asc())
    )
    return [InvitationSummaryOut.model_validate(i) for i in result.scalars().all()]


@invitations_router.delete("/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    result = await session.execute(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.tenant_id == uuid.UUID(claims.tid),
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Invitation not found.",
        )
    if invitation.accepted_at is not None:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="Invitation already accepted.",
        )
    await session.delete(invitation)


@invitations_router.post("/accept", status_code=201)
async def accept_invitation(body: InvitationAcceptIn) -> dict:
    invitation_identity = await find_invitation(hash_token(body.token))

    if invitation_identity is None or invitation_identity.accepted_at is not None:
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid or already accepted invitation.",
        )

    if datetime.fromisoformat(invitation_identity.expires_at) < datetime.now(UTC):
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invitation expired.",
        )

    # users.email e UNIQUE a livello globale: senza questo controllo un invito
    # a un indirizzo gia registrato usciva come 500 (violazione di vincolo).
    if await find_user_by_email(invitation_identity.email) is not None:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="Email already registered.",
        )

    tenant_id = uuid.UUID(invitation_identity.tenant_id)
    user_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        tenant_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = tenant_result.scalar_one()
        if tenant.status != TenantStatus.ACTIVE:
            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="Invalid or already accepted invitation.",
            )

        invitation_result = await session.execute(
            select(Invitation)
            .where(Invitation.id == uuid.UUID(invitation_identity.id))
            .with_for_update()
        )
        invitation = invitation_result.scalar_one()
        if invitation.accepted_at is not None:
            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="Invalid or already accepted invitation.",
            )

        password_hash = await asyncio.to_thread(hash_password, body.password)
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email=invitation.email,
            password_hash=password_hash,
            role=invitation.role,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        invitation.accepted_at = datetime.now(UTC)

    return {"user_id": str(user_id), "tenant_id": str(tenant_id)}
