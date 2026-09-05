"""Add planar/volumetric shape flag and CSS 3D transform columns on objects.

``is_3d`` is nullable so existing rows stay volumetric by convention
(NULL → treat as True). CSS columns default to identity tilt.

Revision ID: 0010_object_shape_css_rotation
Revises: 0009_local_user_password
Create Date: 2026-09-05

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010_object_shape_css_rotation"
down_revision: Union[str, None] = "0009_local_user_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_PERSPECTIVE_PX = 800.0


def upgrade() -> None:
    op.add_column(
        "objects",
        sa.Column("is_3d", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "objects",
        sa.Column(
            "css_rotate_x_deg",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "objects",
        sa.Column(
            "css_rotate_y_deg",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "objects",
        sa.Column(
            "css_rotate_z_deg",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "objects",
        sa.Column(
            "css_perspective_px",
            sa.Float(),
            server_default=str(_DEFAULT_PERSPECTIVE_PX),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("objects", "css_perspective_px")
    op.drop_column("objects", "css_rotate_z_deg")
    op.drop_column("objects", "css_rotate_y_deg")
    op.drop_column("objects", "css_rotate_x_deg")
    op.drop_column("objects", "is_3d")
