from __future__ import annotations

"""SQLAlchemy models and engine/session plumbing for Postgres-backed metadata.

Durable blob storage (cutout PNGs, GLBs, novel-view caches) stays on local
disk regardless of this module — see `core/object_storage.py`. Only session
and object *metadata* (previously the four JSON sidecars plus per-object
`{uid}_{id}_meta.json` files) lives here.
"""
