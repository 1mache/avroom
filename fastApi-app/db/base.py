from __future__ import annotations

"""Shared declarative base every ORM model inherits from."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all `db.models` tables."""
