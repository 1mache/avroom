"""Ensure the fixed local dev user exists with a known password ("admin").

`core.auth.single_user.get_or_create_default_user` (and 0002/0007 before this
migration) only ever run from an `AUTH_MODE=single_user` code path. A machine
that boots straight into `AUTH_MODE=jwt` against a fresh database never
exercises either, so the fixed local user (avroom-team@proton.me) would have
no row -- and no way to log in as it via `POST /auth/login` -- at all. This
migration makes the row (and its password) unconditional: insert it if the id
is missing, backfill the password if the row already exists with none set
(an older single_user-only install).

Revision ID: 0009_local_user_password
Revises: 0008_projects
Create Date: 2026-09-04

"""
from __future__ import annotations

from typing import Sequence, Union

import bcrypt
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_local_user_password"
down_revision: Union[str, None] = "0008_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"
_LOCAL_USER_EMAIL = "avroom-team@proton.me"
_LOCAL_USER_PASSWORD = "admin"


def upgrade() -> None:
    password_hash = bcrypt.hashpw(_LOCAL_USER_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    op.execute(
        sa.text(
            """
            INSERT INTO users (id, email, password_hash, created_at, is_active, is_admin)
            VALUES (:id, :email, :password_hash, now(), true, true)
            ON CONFLICT (id) DO UPDATE
            SET password_hash = EXCLUDED.password_hash
            WHERE users.password_hash IS NULL
            """
        ).bindparams(id=_LOCAL_USER_ID, email=_LOCAL_USER_EMAIL, password_hash=password_hash)
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE users SET password_hash = NULL WHERE id = :id").bindparams(id=_LOCAL_USER_ID))
