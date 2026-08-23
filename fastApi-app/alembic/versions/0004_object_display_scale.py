"""Add display_scale column to objects table.

Depth rescale / smart-paste persist cumulative UI scale in metadata while
leaving the cutout PNG at original resolution.

Revision ID: 0004_object_display_scale
Revises: 0003_jobs
Create Date: 2026-08-23

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_object_display_scale"
down_revision: Union[str, None] = "0003_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "objects",
        sa.Column("display_scale", sa.Float(), server_default="1.0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("objects", "display_scale")
