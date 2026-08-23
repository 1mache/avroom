"""Update the fixed local dev user's email to the team notification inbox.

The AUTH_MODE=single_user local user (id 00000000-0000-0000-0000-000000000001)
was provisioned with email "local@avroom.dev". Pipeline-completion emails now
go to the team inbox in local dev, so existing rows need updating — new rows
already get the new constant from core/auth/single_user.py.

Revision ID: 0002_local_user_email
Revises: 0001_initial
Create Date: 2026-08-22

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_local_user_email"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"
_NEW_EMAIL = "avroom-team@proton.me"
_OLD_EMAIL = "local@avroom.dev"


def upgrade() -> None:
    op.execute(
        f"UPDATE users SET email = '{_NEW_EMAIL}' WHERE id = '{_LOCAL_USER_ID}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE users SET email = '{_OLD_EMAIL}' WHERE id = '{_LOCAL_USER_ID}'"
    )
