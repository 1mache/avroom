from __future__ import annotations

"""ORM models backing session/object metadata (Postgres, both local and cloud).

Blob artifacts (cutout PNGs, GLBs, novel-view caches) are not modeled here —
they stay on local disk and are addressed by `{uid}_{object_id}_...` paths in
`core/object_storage.py`, unchanged by this module.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def _new_uuid_str() -> str:
    return str(uuid.uuid4())


def _now_utc() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """A registered user. In `AUTH_MODE=single_user`, exactly one fixed row exists."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)

    sessions: Mapped[list["SessionRow"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class SessionRow(Base):
    """One editing session (the `uid` used throughout the API), owned by a user."""

    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_sessions_user_id_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_changed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    history_min: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    history_cursor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    history_head: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")
    objects: Mapped[list["ObjectRow"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ObjectRow(Base):
    """Metadata for one finalized object within a session (replaces `*_meta.json`)."""

    __tablename__ = "objects"
    __table_args__ = (UniqueConstraint("session_id", "object_id", name="uq_objects_session_id_object_id"),)

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid_str)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    average_depth: Mapped[float] = mapped_column(Float, nullable=False)
    source_elevation_deg: Mapped[float] = mapped_column(Float, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)
    clone_root_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    clone_root_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clone_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offset_x: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    offset_y: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    display_scale: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    stage_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    session: Mapped[SessionRow] = relationship(back_populates="objects")


class JobRow(Base):
    """A durable, user-owned unit of queued work (segment / inpaint / generate_3d).

    The table only ever holds in-flight work, unconsumed segment results, and
    failures — a successful inpaint/generate_3d row is deleted once its real
    result (an `ObjectRow` / GLB file) exists, so this never grows unbounded.
    `user_id` is the routing key: it is how a result gets back to the caller
    that queued it once multiple users share one queue (see
    `core/auth/identity.py`).
    """

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created_at", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid_str)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
