from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    """Request payload for POST /auth/signup."""

    email: Annotated[EmailStr, Field(description="New account's email address.")]
    password: Annotated[
        str,
        Field(
            min_length=8,
            max_length=72,
            description="Plaintext password, 8-72 bytes (bcrypt's hard limit).",
        ),
    ]


class LoginRequest(BaseModel):
    """Request payload for POST /auth/login."""

    email: Annotated[EmailStr, Field(description="Account email address.")]
    password: Annotated[
        str,
        Field(min_length=1, description="Plaintext password. No length policy enforced here."),
    ]


class TokenResponse(BaseModel):
    """Response for POST /auth/signup and POST /auth/login."""

    access_token: Annotated[str, Field(description="Signed JWT; send as 'Authorization: Bearer <token>'.")]
    token_type: Annotated[Literal["bearer"], Field(default="bearer")] = "bearer"


class MeResponse(BaseModel):
    """Response for GET /auth/me."""

    user_id: Annotated[str, Field(description="Caller's user id, resolved from the bearer token.")]
    email: Annotated[EmailStr, Field(description="Caller's account email.")]
    is_admin: Annotated[bool, Field(description="Whether the caller may use admin-only tools.")]
