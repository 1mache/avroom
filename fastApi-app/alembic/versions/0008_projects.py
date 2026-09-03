"""Add projects table; group existing sessions under a per-user "My Rooms" project.

Introduces the Project layer above sessions (rooms): `User -> Project -> Room`.
`sessions.project_id` is added nullable first so every existing row can be
backfilled, then tightened to NOT NULL -- no orphan rooms, no project-less
bucket to support in the app. One "My Rooms" project is created per distinct
`sessions.user_id`, plus one for the fixed local dev user
(core/auth/single_user.py::LOCAL_USER_ID) even if it has no sessions yet,
mirroring 0007_user_is_admin's handling of that same fixed row.

The old `uq_sessions_user_id_name` constraint (room names unique per user)
is replaced with `uq_sessions_project_id_name` (unique per project) -- two
different projects may each have a room called "Living room".

Revision ID: 0008_projects
Revises: 0007_user_is_admin
Create Date: 2026-09-03

"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_projects"
down_revision: Union[str, None] = "0007_user_is_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"
_DEFAULT_PROJECT_NAME = "My Rooms"


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_projects_user_id_name"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.add_column("sessions", sa.Column("project_id", sa.String(length=36), nullable=True))

    conn = op.get_bind()
    now = datetime.now(UTC)

    user_ids = {row[0] for row in conn.execute(sa.text("SELECT DISTINCT user_id FROM sessions"))}
    user_ids.add(_LOCAL_USER_ID)  # provisioned even with zero sessions, like 0007 does for is_admin

    # A distinct-user_id sweep is a handful of rows in practice (one project
    # per user, not per session) -- no need for a bulk-insert path here.
    for user_id in user_ids:
        if conn.execute(sa.text("SELECT 1 FROM users WHERE id = :uid"), {"uid": user_id}).first() is None:
            continue  # a stray sessions.user_id with no matching user row would violate the FK below
        project_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO projects (id, user_id, name, created_at) "
                "VALUES (:id, :user_id, :name, :created_at)"
            ),
            {"id": project_id, "user_id": user_id, "name": _DEFAULT_PROJECT_NAME, "created_at": now},
        )
        conn.execute(
            sa.text("UPDATE sessions SET project_id = :project_id WHERE user_id = :user_id"),
            {"project_id": project_id, "user_id": user_id},
        )

    op.alter_column("sessions", "project_id", nullable=False)
    op.create_foreign_key(
        "fk_sessions_project_id", "sessions", "projects", ["project_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_sessions_project_id", "sessions", ["project_id"])

    op.drop_constraint("uq_sessions_user_id_name", "sessions", type_="unique")
    op.create_unique_constraint("uq_sessions_project_id_name", "sessions", ["project_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_sessions_project_id_name", "sessions", type_="unique")
    op.create_unique_constraint("uq_sessions_user_id_name", "sessions", ["user_id", "name"])
    op.drop_index("ix_sessions_project_id", table_name="sessions")
    op.drop_constraint("fk_sessions_project_id", "sessions", type_="foreignkey")
    op.drop_column("sessions", "project_id")
    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
