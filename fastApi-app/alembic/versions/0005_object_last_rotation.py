"""Persist last novel-view rotation angles on objects.

Revision ID: 0005_object_last_rotation
Revises: 0004_object_display_scale
Create Date: 2026-08-28

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_object_last_rotation"
down_revision: Union[str, None] = "0004_object_display_scale"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "objects",
        sa.Column("rotation_azimuth_deg", sa.Float(), nullable=True),
    )
    op.add_column(
        "objects",
        sa.Column("rotation_relative_elevation_deg", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("objects", "rotation_relative_elevation_deg")
    op.drop_column("objects", "rotation_azimuth_deg")
