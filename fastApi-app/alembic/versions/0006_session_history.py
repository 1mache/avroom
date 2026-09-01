"""Add background history stack columns to sessions and stage_seq to objects.

Revision ID: 0006_session_history
Revises: 0005_object_last_rotation
Create Date: 2026-09-01

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_session_history"
down_revision: Union[str, None] = "0005_object_last_rotation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("history_min", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "sessions",
        sa.Column("history_cursor", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "sessions",
        sa.Column("history_head", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "objects",
        sa.Column("stage_seq", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("objects", "stage_seq")
    op.drop_column("sessions", "history_head")
    op.drop_column("sessions", "history_cursor")
    op.drop_column("sessions", "history_min")
