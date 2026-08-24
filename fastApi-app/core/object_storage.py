from __future__ import annotations

"""Filesystem path helpers for finalized per-object artifacts.

This module centralizes all ``{uid}_{object_id}_…`` path construction so
callers never hand-roll the naming convention.  It is intentionally separate
from :mod:`mask_cache`, which handles *temporary* segmentation candidates
(``{uid}_mask_{N}_…``).
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def remove_file(path: Path) -> int:
    """Delete *path* if it exists and return how many files that removed (0 or 1).

    Returning a count rather than a bool lets callers accumulate a total with
    ``removed += remove_file(...)`` instead of repeating an exists/unlink pair.
    """

    if not path.exists():
        return 0
    path.unlink(missing_ok=True)
    return 1


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


def legacy_object_cutout_path(base_dir: Path, uid: str) -> Path:
    """Return the pre-numbering cutout path ``{uid}_cutout.png``.

    Written by backend versions that predate per-object numbering; still read
    (and deleted) as object id 0 for those sessions.
    """

    return base_dir / f"{uid}_cutout.png"


def legacy_object_glb_path(glb_dir: Path, uid: str) -> Path:
    """Return the pre-numbering GLB path ``{uid}.glb`` (see :func:`legacy_object_cutout_path`)."""

    return glb_dir / f"{uid}.glb"


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
        legacy = legacy_object_cutout_path(base_dir, uid)
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
        legacy = legacy_object_glb_path(glb_dir, uid)
        logger.debug(
            "resolve_object_glb_path: numbered path absent, using legacy: uid=%s path=%s",
            uid,
            legacy,
        )
        return legacy
    return numbered


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


def session_preview_path(base_dir: Path, uid: str) -> Path:
    """Return the dashboard thumbnail path for one session.

    The path is always ``base_dir / "{uid}_preview.jpg"``; no fallback logic
    is applied. JPEG (not PNG) because the thumbnail is a lossy, small-file
    compositing of the background plus every visible cutout — matching what
    the frontend's ``composeSessionPreview`` already produces.

    Args:
        base_dir: Directory that contains session artifacts.
        uid: Session UID.

    Returns:
        A :class:`~pathlib.Path` for the session preview file.
    """
    return base_dir / f"{uid}_preview.jpg"


def copy_file_preserving_mtime(source: Path, destination: Path) -> Path:
    """Copy *source* to *destination*, preserving timestamps via ``copy2``."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def copy_object_artifacts(
    *,
    base_dir: Path,
    glb_dir: Path,
    uid: str,
    source_object_id: int,
    dest_object_id: int,
) -> list[Path]:
    """Copy per-object disk artifacts from *source_object_id* to *dest_object_id*.

    Copies the cutout (required) and optional GLB. Session-level files
    (background, depth, original, camera calib) are never touched.

    Returns:
        Paths written for the destination object (for rollback on failure).

    Raises:
        FileNotFoundError: When the source cutout is missing.
    """

    source_cutout = resolve_object_cutout_path(base_dir, uid, source_object_id)
    if not source_cutout.exists():
        raise FileNotFoundError(
            f"Source cutout not found for uid='{uid}' object_id={source_object_id}"
        )

    written: list[Path] = []
    try:
        dest_cutout = object_cutout_path(base_dir, uid, dest_object_id)
        copy_file_preserving_mtime(source_cutout, dest_cutout)
        written.append(dest_cutout)
        logger.debug(
            "Copied cutout: uid=%s source_id=%d dest_id=%d path=%s",
            uid,
            source_object_id,
            dest_object_id,
            dest_cutout,
        )

        source_glb = resolve_object_glb_path(glb_dir, uid, source_object_id)
        if source_glb.exists():
            dest_glb = object_glb_path(glb_dir, uid, dest_object_id)
            copy_file_preserving_mtime(source_glb, dest_glb)
            written.append(dest_glb)
            logger.debug(
                "Copied GLB: uid=%s source_id=%d dest_id=%d path=%s",
                uid,
                source_object_id,
                dest_object_id,
                dest_glb,
            )

        logger.info(
            "Copied object artifacts: uid=%s source_id=%d dest_id=%d files=%d",
            uid,
            source_object_id,
            dest_object_id,
            len(written),
        )
        return written
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise


def delete_object_artifact_files(
    *,
    base_dir: Path,
    glb_dir: Path,
    uid: str,
    object_id: int,
) -> int:
    """Delete per-object artifact files for *object_id*. Returns files removed.

    Used to roll back a failed clone so ``list_object_ids`` never sees a cutout
    without matching metadata. Metadata itself lives in Postgres
    (`core/object_metadata.py`), not on disk — callers delete that row
    separately.
    """

    removed = remove_file(object_cutout_path(base_dir, uid, object_id))
    removed += remove_file(object_glb_path(glb_dir, uid, object_id))

    logger.debug(
        "Deleted object artifact files: uid=%s object_id=%d removed=%d",
        uid,
        object_id,
        removed,
    )
    return removed


def delete_legacy_object_artifacts(*, base_dir: Path, glb_dir: Path, uid: str) -> int:
    """Delete the pre-numbering ``{uid}_cutout.png`` / ``{uid}.glb`` pair.

    ``delete_object_artifact_files`` only knows the numbered filenames
    (``object_cutout_path`` / ``object_glb_path``), so deleting object id 0 on
    a session created before per-object numbering leaves these legacy files
    behind — and since ``list_object_ids`` treats a present legacy cutout as
    id 0, the "deleted" object would reappear on the next listing. Callers
    should invoke this alongside :func:`delete_object_artifact_files` when
    deleting object id 0.

    Returns:
        Number of files removed (0, 1, or 2).
    """
    removed = remove_file(legacy_object_cutout_path(base_dir, uid))
    removed += remove_file(legacy_object_glb_path(glb_dir, uid))
    return removed
