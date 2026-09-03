"""Add is_admin flag to users; grant it to the fixed local dev user.

Admin gates the /debug router and the upload endpoint's skip_validation
flag -- see core/auth/admin.py. No admin UI/API exists to grant this; it is
flipped by hand in SQL. server_default false covers every existing row, then
the UPDATE re-grants the local dev user (id 00000000-0000-0000-0000-000000000001)
so single_user-mode local development keeps both tools, mirroring
0002_local_user_email's pattern for the same fixed row.

Revision ID: 0007_user_is_admin
Revises: 0006_session_history
Create Date: 2026-09-03

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_user_is_admin"
down_revision: Union[str, None] = "0006_session_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(f"UPDATE users SET is_admin = true WHERE id = '{_LOCAL_USER_ID}'")


def downgrade() -> None:
    op.drop_column("users", "is_admin")
