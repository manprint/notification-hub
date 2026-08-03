import secrets
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import PROBLEM_TYPES, Problem


class AccessClaims(BaseModel):
    sub: str
    tid: str
    role: str
    exp: int
    iat: int
    jti: str


_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hash_value: str) -> bool:
    """InvalidHashError oltre a VerifyMismatchError: una riga con un
    password_hash non in formato argon2 (dato importato o seed a mano) faceva
    uscire un 500 dal login invece di un 401."""
    try:
        _ph.verify(hash_value, password)
        return True
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def create_access_token(user_id: str, tenant_id: str, role: str) -> tuple[str, int]:
    settings = get_settings()
    # datetime.utcnow() e naive: .timestamp() lo interpreta nel fuso ORARIO
    # LOCALE del sistema, non in UTC, producendo un epoch sbagliato se il
    # server non gira in UTC. datetime.now(UTC) e tz-aware ed e corretto.
    now = datetime.now(UTC)
    exp_minutes = settings.access_token_ttl_minutes
    exp_time = now + timedelta(minutes=exp_minutes)

    claims = {
        "sub": user_id,
        "tid": tenant_id,
        "role": role,
        "exp": int(exp_time.timestamp()),
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
    }

    token = jwt.encode(claims, settings.notifyhub_secret_key, algorithm="HS256")
    return token, exp_minutes * 60


def decode_access_token(token: str) -> AccessClaims:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.notifyhub_secret_key, algorithms=["HS256"])
        return AccessClaims(**claims)
    except Exception as e:
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid or expired token.",
        ) from e


def new_refresh_token() -> tuple[str, str]:
    token_plain = secrets.token_urlsafe(32)
    token_hash = hash_token(token_plain)
    return token_plain, token_hash


def hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()
