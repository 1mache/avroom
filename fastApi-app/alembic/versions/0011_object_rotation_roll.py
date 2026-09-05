"""Wire unused rotation angle columns and add roll.

``rotation_azimuth_deg`` / ``rotation_relative_elevation_deg`` already exist
from 0005 but were never mapped on ObjectRow. This revision only adds
``rotation_roll_deg`` for screen-space Z baked into the persisted PNG.

Revision ID: 0011_object_rotation_roll
Revises: 0010_object_shape_css_rotation
Create Date: 2026-09-05

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_object_rotation_roll"
down_revision: Union[str, None] = "0010_object_shape_css_rotation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "objects",
        sa.Column("rotation_roll_deg", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("objects", "rotation_roll_deg")
