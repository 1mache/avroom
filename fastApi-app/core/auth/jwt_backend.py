from __future__ import annotations

"""Password hashing and JWT issuance/verification for `AUTH_MODE=jwt`.

Uses `bcrypt` directly, not `passlib[bcrypt]` -- passlib 1.7.4 probes
`bcrypt.__about__.__version__`, which the installed bcrypt (>=4.1) no longer
has, and falls into a self-test path that raises
`ValueError: password cannot be longer than 72 bytes` on every hash call,
even for short passwords (verified locally). Raw `bcrypt.hashpw`/`checkpw`
has no such issue and needs no extra dependency.

No `fastapi.security` usage here (matching the rest of the repo, which has
none): `HTTPBearer`'s default `auto_error=True` raises 403, not 401, on a
missing header, and this module wants 401 throughout. `core/auth/identity.py`
reads the `Authorization` header itself instead.
"""

import logging
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from settings import get_jwt_expire_minutes, get_jwt_secret

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"


class AuthError(Exception):
    """Raised for any password/token failure; routes map this to 401."""


def _secret() -> str:
    secret = get_jwt_secret()
    if not secret:
        raise RuntimeError("JWT_SECRET must be set when AUTH_MODE=jwt")
    return secret


def ensure_configured() -> None:
    """Raise if `AUTH_MODE=jwt` is active but `JWT_SECRET` is unset.

    Called once at app startup (see `main.py`'s `lifespan`) so a missing
    secret fails the container at boot, not on the first login request.
    """
    _secret()


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*, suitable for `User.password_hash`."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Return whether *plain* matches *hashed*.

    False (never a raised exception) on any mismatch, including a *plain*
    over bcrypt's 72-byte hard limit -- `schemas.auth.LoginRequest` doesn't
    bound password length (unlike signup), so a malicious long password must
    degrade to "wrong password", not a 500.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def issue_token(user_id: str) -> str:
    """Return a signed JWT whose `sub` claim is *user_id*."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=get_jwt_expire_minutes()),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_token(token: str) -> str:
    """Return the `sub` claim of a valid, unexpired *token*.

    Raises:
        AuthError: On any signature/expiry/format failure.
    """
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid or expired token") from exc
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise AuthError("Token missing 'sub' claim")
    return sub
