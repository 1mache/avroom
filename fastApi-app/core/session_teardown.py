from __future__ import annotations

"""Shared session-deletion body.

Extracted from `api/sessions.py::delete_session` so `DELETE /projects/{id}`
(cascading to every room inside it) can reuse the exact same blob cleanup
instead of re-deriving it -- a project delete that skipped this would leak
every deleted room's cutouts/GLBs/caches on disk.
"""

import logging

from core.camera_calib_cache import delete_session_camera_calib
from core.depth_cache import delete_session_depth_maps
from core.mask_cache import delete_candidates
from core.normal_cache import delete_session_normal_maps
from core.image_processing import debug_click_image_path
from core.object_metadata import list_object_ids
from core.object_storage import (
    current_background_path,
    delete_session_background_history,
    legacy_object_cutout_path,
    legacy_object_glb_path,
    object_cutout_path,
    object_glb_path,
    object_rotated_path,
    remove_file,
    session_preview_path,
)
from core.repositories.session_repo import delete_session as delete_session_row
from settings import get_3d_storage_dir, get_image_storage_dir

logger = logging.getLogger(__name__)


def delete_session_and_files(uid: str) -> int:
    """Delete one session's DB row (cascading to its objects) and every file it owns.

    Missing files are silently ignored so this is safe to call more than
    once. Returns the number of files removed (informational only).
    """
    storage_dir = get_image_storage_dir()
    removed = 0

    obj_ids = list_object_ids(uid)
    delete_session_row(uid)

    for path in storage_dir.glob(f"{uid}.*"):
        path.unlink(missing_ok=True)
        removed += 1

    three_d_dir = get_3d_storage_dir()
    for path in (
        current_background_path(storage_dir, uid),
        legacy_object_cutout_path(storage_dir, uid),
        session_preview_path(storage_dir, uid),
        debug_click_image_path(storage_dir, uid),
        legacy_object_glb_path(three_d_dir, uid),
    ):
        removed += remove_file(path)

    delete_candidates(storage_dir, uid)

    for oid in obj_ids:
        removed += remove_file(object_cutout_path(storage_dir, uid, oid))
        removed += remove_file(object_rotated_path(storage_dir, uid, oid))
        removed += remove_file(object_glb_path(three_d_dir, uid, oid))

    removed += delete_session_depth_maps(storage_dir, uid)
    removed += delete_session_normal_maps(storage_dir, uid)
    removed += delete_session_camera_calib(storage_dir, uid)
    removed += delete_session_background_history(storage_dir, uid)

    return removed
