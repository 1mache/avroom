from __future__ import annotations

"""Filesystem path helpers for finalized per-object artifacts.

This module centralizes all ``{uid}_{object_id}_…`` path construction so
callers never hand-roll the naming convention.  It is intentionally separate
from :mod:`mask_cache`, which handles *temporary* segmentation candidates
(``{uid}_mask_{N}_…``).
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def object_cutout_path(base_dir: Path, uid: str, object_id: int) -> Path:
    """Return the canonical path for a finalized object cutout PNG.

    The path is always ``base_dir / "{uid}_{object_id}_cutout.png"`` regardless
    of whether the file exists.

    Args:
        base_dir: Directory that contains session artifacts.
        uid: Session UID.
        object_id: Zero-based integer object identifier.

    Returns:
        Absolute (or relative, depending on *base_dir*) :class:`~pathlib.Path`.
    """
    return base_dir / f"{uid}_{object_id}_cutout.png"


def resolve_object_cutout_path(base_dir: Path, uid: str, object_id: int) -> Path:
    """Return the object cutout path, falling back to the legacy name for id 0.

    For ``object_id == 0`` only: if the numbered file
    ``{uid}_0_cutout.png`` does not exist, return the legacy path
    ``{uid}_cutout.png`` instead (written by earlier backend versions).
    For any other *object_id* the numbered path is returned unconditionally.

    Args:
        base_dir: Directory that contains session artifacts.
        uid: Session UID.
        object_id: Zero-based integer object identifier.

    Returns:
        A :class:`~pathlib.Path` pointing to the best available cutout file.
    """
    numbered = object_cutout_path(base_dir, uid, object_id)
    if object_id == 0 and not numbered.exists():
        legacy = base_dir / f"{uid}_cutout.png"
        logger.debug(
            "resolve_object_cutout_path: numbered path absent, using legacy: uid=%s path=%s",
            uid,
            legacy,
        )
        return legacy
    return numbered


def object_glb_path(glb_dir: Path, uid: str, object_id: int) -> Path:
    """Return the canonical path for a finalized object GLB 3-D model.

    The path is always ``glb_dir / "{uid}_{object_id}.glb"`` regardless of
    whether the file exists.

    Args:
        glb_dir: Directory that contains GLB artifacts.
        uid: Session UID.
        object_id: Zero-based integer object identifier.

    Returns:
        A :class:`~pathlib.Path` for the numbered GLB file.
    """
    return glb_dir / f"{uid}_{object_id}.glb"


def resolve_object_glb_path(glb_dir: Path, uid: str, object_id: int) -> Path:
    """Return the GLB path, falling back to the legacy name for id 0.

    For ``object_id == 0`` only: if the numbered file ``{uid}_0.glb`` does not
    exist, return the legacy path ``{uid}.glb`` instead.
    For any other *object_id* the numbered path is returned unconditionally.

    Args:
        glb_dir: Directory that contains GLB artifacts.
        uid: Session UID.
        object_id: Zero-based integer object identifier.

    Returns:
        A :class:`~pathlib.Path` pointing to the best available GLB file.
    """
    numbered = object_glb_path(glb_dir, uid, object_id)
    if object_id == 0 and not numbered.exists():
        legacy = glb_dir / f"{uid}.glb"
        logger.debug(
            "resolve_object_glb_path: numbered path absent, using legacy: uid=%s path=%s",
            uid,
            legacy,
        )
        return legacy
    return numbered


def list_object_ids(base_dir: Path, uid: str) -> list[int]:
    """Return sorted list of object ids for *uid* found in *base_dir*.

    Scans *base_dir* for files matching the pattern
    ``^{uid}_(<digits>)_cutout\\.png$``.  Because ``\\d+`` only matches
    decimal digits, candidate files like ``{uid}_mask_3_cutout.png`` are
    **not** picked up — "mask_3" is not all-digits.

    Additionally, if the legacy file ``{uid}_cutout.png`` exists, id ``0`` is
    included (deduplicated).

    Args:
        base_dir: Directory that contains session artifacts.
        uid: Session UID.

    Returns:
        Sorted ascending list of integer object ids.
    """
    pattern = re.compile(r"^" + re.escape(uid) + r"_(\d+)_cutout\.png$")
    ids: set[int] = set()

    if base_dir.is_dir():
        for entry in base_dir.iterdir():
            m = pattern.match(entry.name)
            if m:
                ids.add(int(m.group(1)))

        legacy = base_dir / f"{uid}_cutout.png"
        if legacy.exists():
            ids.add(0)

    return sorted(ids)


def next_object_id(base_dir: Path, uid: str) -> int:
    """Return the next available object id for *uid*.

    If no objects have been finalised yet, returns ``0``.  Otherwise returns
    ``max(existing_ids) + 1``.

    Args:
        base_dir: Directory that contains session artifacts.
        uid: Session UID.

    Returns:
        Non-negative integer to use as the id for the next object.
    """
    existing = list_object_ids(base_dir, uid)
    if not existing:
        return 0
    return max(existing) + 1


def current_background_path(base_dir: Path, uid: str) -> Path:
    """Return the path of the cumulative background canvas for a session.

    This is a single PNG that accumulates all inpainting results so far.
    The path is always ``base_dir / "{uid}_background.png"``; no fallback
    logic is applied.

    Args:
        base_dir: Directory that contains session artifacts.
        uid: Session UID.

    Returns:
        A :class:`~pathlib.Path` for the session background file.
    """
    return base_dir / f"{uid}_background.png"
