"""Account creation, login, and caller identity.

Not session-scoped, so this router carries no `require_session_owner`
dependency -- and `/auth/login`/`/auth/signup` must be reachable with no
token at all. In `AUTH_MODE=single_user` these routes exist and issue tokens
nobody checks (every other route still resolves the fixed local user); not
conditionally hidden, since a config branch in the route table buys nothing.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth.identity import current_user_id
from core.auth.jwt_backend import hash_password, issue_token, verify_password
from core.notifications import notify_account_created, request_recipient_verification
from db.models import User
from db.session import get_db
from schemas.auth import LoginRequest, MeResponse, SignupRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

_INVALID_CREDENTIALS = "Invalid email or password"


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(request: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a new account and return a usable token immediately."""
    logger.info("Signup requested: email=%s", request.email)
    user = User(
        id=str(uuid.uuid4()),
        email=request.email,
        password_hash=hash_password(request.password),
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        logger.warning("Signup rejected — email already registered: email=%s", request.email)
        raise HTTPException(status_code=409, detail="Email already registered") from exc

    logger.info("Signup succeeded: user_id=%s", user.id)
    request_recipient_verification(user.email)
    notify_account_created(user.email)
    return TokenResponse(access_token=issue_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Verify credentials and return a token.

    One failure path for unknown email, wrong password, and a deactivated
    account -- identical 401 for all three, so a caller can never learn
    which email is registered from the response alone.
    """
    user = db.query(User).filter(User.email == request.email).one_or_none()
    if (
        user is None
        or user.password_hash is None
        or not verify_password(request.password, user.password_hash)
        or not user.is_active
    ):
        logger.warning("Login rejected: email=%s", request.email)
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)

    logger.info("Login succeeded: user_id=%s", user.id)
    return TokenResponse(access_token=issue_token(user.id))


@router.get("/me", response_model=MeResponse)
def get_me(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)) -> MeResponse:
    """Return the caller's own id and email, proving a token round-trips."""
    user = db.get(User, user_id)
    if user is None:
        # Only reachable if the account behind a still-valid token was
        # deleted -- decode_token doesn't re-check the users table (the
        # signature is the proof; see core/auth/identity.py).
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return MeResponse(user_id=user.id, email=user.email, is_admin=user.is_admin)
