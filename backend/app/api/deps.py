import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims, decode_access_token
from app.db.session import tenant_session
from app.db.types import UserRole


def client_ip(request: Request) -> str:
    """IP di origine della richiesta, per i rate limit su (chiave, IP).

    `X-Forwarded-For` viene letto SOLO se la connessione arriva da un proxy
    dichiarato in `TRUSTED_PROXIES`: altrove e un header che il client scrive da
    se, e fiducia cieca renderebbe ogni limite per IP aggirabile a piacere.

    Dietro il reverse proxy del deploy standard (nginx, spec 13) l'IP della
    connessione e sempre quello del proxy: senza questa risoluzione tutti i
    client condividono la stessa chiave e un limite pensato per fermare il
    singolo mittente diventa un limite globale, che chiunque puo saturare per
    tutti gli altri.
    """
    settings = get_settings()
    host = request.client.host if request.client else "unknown"
    if host in settings.trusted_proxies_list:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return host


async def current_claims(authorization: str | None = Header(default=None)) -> AccessClaims:
    # authorization e opzionale a livello di validazione FastAPI apposta: un header
    # assente deve rispondere 401 applicativo, non 422 di Pydantic (vedi docs/REVIEW.md F15).
    if authorization is None or not authorization.startswith("Bearer "):
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid authorization header.",
        )
    token = authorization[7:]
    return decode_access_token(token)


async def db(claims: AccessClaims = Depends(current_claims)) -> AsyncIterator[AsyncSession]:  # noqa: B008
    async with tenant_session(uuid.UUID(claims.tid)) as session:
        yield session


def require_role(*roles: str) -> Any:
    async def check_role(claims: AccessClaims = Depends(current_claims)) -> AccessClaims:  # noqa: B008
        if claims.role not in roles:
            raise Problem(
                status=403,
                type=PROBLEM_TYPES["forbidden"],
                title="Forbidden",
                detail="Insufficient permissions.",
            )
        return claims

    return check_role


async def require_owner(  # noqa: B008
    claims: AccessClaims = Depends(require_role(UserRole.OWNER)),  # noqa: B008
) -> AccessClaims:
    return claims


async def require_admin(  # noqa: B008
    claims: AccessClaims = Depends(require_role(UserRole.OWNER, UserRole.ADMIN)),  # noqa: B008
) -> AccessClaims:
    return claims


async def require_member(  # noqa: B008
    claims: AccessClaims = Depends(require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.MEMBER)),  # noqa: B008
) -> AccessClaims:
    return claims


async def require_viewer(  # noqa: B008
    claims: AccessClaims = Depends(  # noqa: B008
        require_role(UserRole.OWNER, UserRole.ADMIN, UserRole.MEMBER, UserRole.VIEWER)  # noqa: B008
    ),
) -> AccessClaims:
    return claims
