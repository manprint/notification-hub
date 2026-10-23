import ipaddress
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
from app.services.audit import (
    AuditContext,
    current_request_id,
    reset_audit_context,
    set_audit_context,
)


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
    host = request.client.host if request.client else "unknown"
    networks = get_settings().trusted_proxy_networks
    peer = _parse_ip(host)
    if peer is None or not _is_trusted(peer, networks):
        return host
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return host

    # Ogni proxy fidato accoda in coda l'indirizzo da cui ha ricevuto la
    # connessione: si scorre da destra, saltando i proxy fidati, e la prima voce
    # non fidata e il client visto dal primo proxy. Una voce che non e un IP
    # valido interrompe la catena: non si puo fidare di nient'altro.
    entries = [entry.strip() for entry in forwarded.split(",")]
    for entry in reversed(entries):
        ip = _parse_ip(entry)
        if ip is None:
            return host
        if not _is_trusted(ip, networks):
            return str(ip)
    # Tutta la catena e di proxy fidati: il client e la voce piu a sinistra.
    leftmost = _parse_ip(entries[0])
    return str(leftmost) if leftmost is not None else host


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """IP canonico, o None se il valore non lo e. Un IPv6 con zona di scope e
    rifiutato: la sua forma testuale puo superare le 45 colonne dell'audit."""
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.scope_id is not None:
            return None
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
    return ip


def _is_trusted(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    return any(ip in network for network in networks)


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


async def audit_scope(  # noqa: B008
    request: Request,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
) -> AsyncIterator[None]:
    """Attore della richiesta, visibile all'hook di audit (services/audit.py).

    Sta qui e non in un middleware perche' l'attore lo dicono i claims del
    token, che il middleware non ha ancora decodificato. Essendo agganciato a
    `db`, copre per costruzione ogni endpoint autenticato: uno nuovo e'
    tracciato senza che nessuno se ne debba ricordare.
    """
    context = AuditContext(
        tenant_id=uuid.UUID(claims.tid),
        actor_user_id=uuid.UUID(claims.sub),
        actor_role=UserRole(claims.role),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=current_request_id(),
    )
    token = set_audit_context(context)
    try:
        yield
    finally:
        reset_audit_context(token)


async def db(  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    _audit: None = Depends(audit_scope),  # noqa: B008
) -> AsyncIterator[AsyncSession]:
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
