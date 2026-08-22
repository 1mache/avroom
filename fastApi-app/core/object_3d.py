from __future__ import annotations

"""Shared GLB cache-or-generate helper for object 3D models.

Used by both `POST /images/novel-view` (which needs a mesh to rotate) and the
`generate_3d` job handler (`core/jobs/handlers.py`) — pulled out of
`api/novel_view.py` so a `core/` module doesn't have to reach into `api/` to
reuse it.
"""

import logging
from pathlib import Path

from core.inference_pool.client import get_inference_client
from core.object_storage import object_glb_path, resolve_object_glb_path
from core.repositories.session_repo import touch_session
from settings import get_3d_storage_dir

logger = logging.getLogger(__name__)


def ensure_object_glb(*, uid: str, object_id: int, cutout_path: Path) -> Path:
    """Return the on-disk GLB for ``(uid, object_id)``, generating it if missing.

    Looks up the cached mesh under the 3D storage dir first (including the
    legacy ``{uid}.glb`` name for object 0). On a miss, runs 3D generation and
    writes the canonical numbered path ``{uid}_{object_id}.glb``.

    Raises:
        RuntimeError: When generation fails or returns empty bytes.
    """

    glb_dir = get_3d_storage_dir()
    glb_dir.mkdir(parents=True, exist_ok=True)
    existing = resolve_object_glb_path(glb_dir, uid, object_id)
    if existing.is_file() and existing.stat().st_size > 0:
        logger.info("3D GLB cache hit: uid=%s object_id=%d path=%s", uid, object_id, existing)
        return existing

    logger.info(
        "3D GLB cache miss; generating: uid=%s object_id=%d cutout=%s", uid, object_id, cutout_path
    )
    glb_bytes = get_inference_client().run_generate_3d(cutout_path=cutout_path)

    if not isinstance(glb_bytes, bytes) or not glb_bytes:
        logger.error("3D generation returned empty bytes: uid=%s object_id=%d", uid, object_id)
        raise RuntimeError("3D generation returned empty GLB bytes")

    out_path = object_glb_path(glb_dir, uid, object_id)
    out_path.write_bytes(glb_bytes)
    touch_session(uid)
    logger.info(
        "3D GLB written: uid=%s object_id=%d bytes=%d path=%s", uid, object_id, len(glb_bytes), out_path
    )
    return out_path
