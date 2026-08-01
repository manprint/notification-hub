from collections.abc import AsyncIterator
from typing import Any

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims, decode_access_token
from app.db.session import tenant_session
from app.db.types import UserRole


async def current_claims(authorization: str = Header(...)) -> AccessClaims:
    if not authorization.startswith("Bearer "):
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid authorization header.",
        )
    token = authorization[7:]
    return decode_access_token(token)


async def db(claims: AccessClaims = Depends(current_claims)) -> AsyncIterator[AsyncSession]:  # noqa: B008
    import uuid

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
