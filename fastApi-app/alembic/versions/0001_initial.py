"""Initial schema: users, sessions, objects.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-18

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("last_changed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_sessions_user_id_name"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "objects",
        sa.Column("uuid", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("average_depth", sa.Float(), nullable=False),
        sa.Column("source_elevation_deg", sa.Float(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clone_root_uuid", sa.String(length=36), nullable=True),
        sa.Column("clone_root_label", sa.String(length=255), nullable=True),
        sa.Column("clone_index", sa.Integer(), nullable=True),
        sa.Column("offset_x", sa.Float(), nullable=False),
        sa.Column("offset_y", sa.Float(), nullable=False),
        sa.UniqueConstraint("session_id", "object_id", name="uq_objects_session_id_object_id"),
    )
    op.create_index("ix_objects_session_id", "objects", ["session_id"])


def downgrade() -> None:
    op.drop_table("objects")
    op.drop_table("sessions")
    op.drop_table("users")
