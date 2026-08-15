from __future__ import annotations

"""Filesystem path helpers for finalized per-object artifacts.

This module centralizes all ``{uid}_{object_id}_…`` path construction so
callers never hand-roll the naming convention.  It is intentionally separate
from :mod:`mask_cache`, which handles *temporary* segmentation candidates
(``{uid}_mask_{N}_…``).
"""

import logging
import re
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


def object_meta_path(base_dir: Path, session_id: str, object_id: int) -> Path:
    """Return the canonical path for one object's metadata JSON file."""

    return base_dir / f"{session_id}_{object_id}_meta.json"


def _novel_view_stem(uid: str, object_id: int, azimuth_deg: float, relative_elevation_deg: float) -> str:
    """Return the shared filename stem identifying one object at one snapped pose."""

    az_key = int(round(azimuth_deg))
    el_key = int(round(relative_elevation_deg))
    return f"{uid}_{object_id}_novel_az{az_key}_el{el_key}"


def object_novel_view_path(
    base_dir: Path,
    uid: str,
    object_id: int,
    azimuth_deg: float,
    relative_elevation_deg: float,
) -> Path:
    """Return the canonical path for a cached novel-view PNG artifact."""

    return base_dir / f"{_novel_view_stem(uid, object_id, azimuth_deg, relative_elevation_deg)}.png"


def object_novel_view_preview_path(
    base_dir: Path,
    uid: str,
    object_id: int,
    azimuth_deg: float,
    relative_elevation_deg: float,
) -> Path:
    """Return the path for a client-rendered novel-view preview placeholder.

    Distinct suffix from :func:`object_novel_view_path` so this best-effort
    stand-in can never be mistaken for a genuine cached synthesis result by
    the read-side cache check in ``POST /images/novel-view``.
    """

    stem = _novel_view_stem(uid, object_id, azimuth_deg, relative_elevation_deg)
    return base_dir / f"{stem}.preview.png"


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

        if legacy_object_cutout_path(base_dir, uid).exists():
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


def list_object_novel_view_paths(base_dir: Path, uid: str, object_id: int) -> list[Path]:
    """Return novel-view and preview PNG paths belonging to one object.

    Matches both genuine cached results (``…_novel_azX_elY.png``) and client
    preview placeholders (``…_novel_azX_elY.preview.png``).
    """

    if not base_dir.is_dir():
        return []

    prefix = f"{uid}_{object_id}_novel_az"
    paths: list[Path] = []
    for entry in base_dir.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if name.startswith(prefix) and name.endswith(".png"):
            paths.append(entry)
    return sorted(paths)


def _rewrite_novel_view_filename(name: str, uid: str, source_id: int, dest_id: int) -> str:
    """Rewrite a novel-view filename from *source_id* to *dest_id* for the same uid."""

    source_prefix = f"{uid}_{source_id}_"
    dest_prefix = f"{uid}_{dest_id}_"
    if not name.startswith(source_prefix):
        raise ValueError(f"Unexpected novel-view filename for rewrite: {name!r}")
    return dest_prefix + name[len(source_prefix) :]


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

    Copies the cutout (required), optional GLB, and any novel-view / preview
    caches. Session-level files (background, depth, original, camera calib)
    are never touched.

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

        for source_novel in list_object_novel_view_paths(base_dir, uid, source_object_id):
            dest_name = _rewrite_novel_view_filename(
                source_novel.name, uid, source_object_id, dest_object_id
            )
            dest_novel = base_dir / dest_name
            copy_file_preserving_mtime(source_novel, dest_novel)
            written.append(dest_novel)

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
    include_metadata: bool = True,
) -> int:
    """Delete per-object artifact files for *object_id*. Returns files removed.

    Used to roll back a failed clone so ``list_object_ids`` never sees a cutout
    without matching metadata.
    """

    removed = remove_file(object_cutout_path(base_dir, uid, object_id))
    removed += remove_file(object_glb_path(glb_dir, uid, object_id))

    for novel_path in list_object_novel_view_paths(base_dir, uid, object_id):
        novel_path.unlink(missing_ok=True)
        removed += 1

    if include_metadata:
        removed += remove_file(object_meta_path(base_dir, uid, object_id))

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
