from __future__ import annotations

"""Shared novel-view PNG cache-or-synthesize helper.

Mirrors `core/object_3d.py::ensure_object_glb`'s cache-or-generate shape: a
disk cache keyed on `(uid, object_id, azimuth_deg, relative_elevation_deg)`,
consulted first, synthesized on a miss. Pulled out of `api/novel_view.py` so
the freshness check, the model call, and the on-disk write live in one place
instead of inline in the route -- the route keeps only HTTP concerns (pose
resolution, the 404/422/500 mapping, stale-preview cleanup, response shape).
"""

import logging
import os
import uuid
from pathlib import Path

from core.image_codec import encode_png
from core.inference_pool.client import get_inference_client
from core.object_3d import ensure_object_glb
from core.object_storage import object_novel_view_path
from core.repositories.session_repo import touch_session
from settings import get_image_storage_dir

logger = logging.getLogger(__name__)


def ensure_novel_view_png(
    *,
    uid: str,
    object_id: int,
    cutout_path: Path,
    azimuth_deg: float,
    relative_elevation_deg: float,
    elevation_deg: float,
    radius: float,
) -> bytes:
    """Return the cached novel-view PNG for a snapped pose, synthesizing on a miss.

    ``(azimuth_deg, relative_elevation_deg)`` is the cache key -- callers are
    expected to have already snapped it onto the HTTP layer's angular grid so
    near-identical requests share one entry.

    A cache hit must be non-empty (guards a write torn by a crash mid-write --
    the same guard `ensure_object_glb` applies to GLBs) and newer than
    ``cutout_path`` (guards staleness: no current code path rewrites a cutout
    PNG in place after creation, but this defends against one appearing
    without silently serving a stale render).

    Raises:
        RuntimeError: When 3D generation or novel-view synthesis fails, via
            ``ensure_object_glb`` or the underlying inference call.
    """

    cache_path = object_novel_view_path(
        get_image_storage_dir(), uid, object_id, azimuth_deg, relative_elevation_deg
    )

    cache_is_fresh = (
        cache_path.is_file()
        and cache_path.stat().st_size > 0
        and cache_path.stat().st_mtime >= cutout_path.stat().st_mtime
    )
    if cache_is_fresh:
        logger.info(
            "novel-view cache hit: uid=%s object_id=%d path=%s", uid, object_id, cache_path
        )
        return cache_path.read_bytes()

    logger.info(
        "novel-view cache miss; synthesizing: uid=%s object_id=%d cutout=%s",
        uid,
        object_id,
        cutout_path,
    )
    glb_path = ensure_object_glb(uid=uid, object_id=object_id, cutout_path=cutout_path)
    result_bgra = get_inference_client().run_novel_view(
        cutout_path=cutout_path,
        elevation_deg=elevation_deg,
        azimuth_deg=azimuth_deg,
        relative_elevation_deg=relative_elevation_deg,
        radius=radius,
        mesh_path=glb_path,
    )

    png_bytes = encode_png(result_bgra, "novel-view")
    _write_atomic(cache_path, png_bytes)
    touch_session(uid)

    logger.info(
        "novel-view synthesized: uid=%s object_id=%d png_bytes=%d shape=%s path=%s",
        uid,
        object_id,
        len(png_bytes),
        result_bgra.shape,
        cache_path,
    )
    return png_bytes


def _write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` via a same-directory temp file + rename.

    Two concurrent requests for the same snapped pose can both miss the cache
    and both synthesize; a bare ``write_bytes`` lets a third reader observe a
    partially written file mid-write. ``os.replace`` is atomic on both POSIX
    and Windows, so a reader always sees either the old file or the complete
    new one, never a torn one.
    """

    tmp_path = path.parent / f"{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        tmp_path.write_bytes(data)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
