"""Read-only artifact serving, plus the dashboard preview sidecar.

Covers everything that just looks up and returns already-computed state: one
object's metadata by UUID, a session's object list, cache-status, and the
raw background/cutout/original/preview files. See ``api/routes.py`` for
upload plus object CRUD/rescale, and ``api/sessions.py`` for session
lifecycle and pipeline submission; all three routers share the ``/images``
prefix and are mounted together in ``main.py``.
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import os

from PIL import Image, UnidentifiedImageError

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from core.image_codec import to_base64_ascii
from core.image_processing import get_image_path
from core.object_metadata import get_object_by_uuid, list_object_ids, load_object_metadata, to_object_metadata_response
from schemas.objects import (
    ObjectInfo,
    ObjectListResponse,
    ObjectMetadataResponse,
    UidCacheStatusResponse,
)
from schemas.sessions import SessionPreviewRequest
from core.object_storage import (
    current_background_path,
    resolve_object_cutout_path,
    resolve_object_glb_path,
    session_preview_path,
)
from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.session_history import get_history_flags
from core.auth.ownership import require_session_owner
from core.repositories.session_repo import SessionNotFoundError, get_session_name, is_session_registered
from settings import get_3d_storage_dir, get_image_storage_dir

router = APIRouter(prefix="/images", tags=["images"], dependencies=[Depends(require_session_owner)])
logger = logging.getLogger(__name__)


@router.get("/objects/{object_uuid}", response_model=ObjectMetadataResponse)
async def get_object_by_uuid_endpoint(object_uuid: str) -> ObjectMetadataResponse:
    """Return metadata for one object searchable by its UUID."""
    logger.debug("Object metadata requested: uuid=%s", object_uuid)
    storage_dir = get_image_storage_dir()
    metadata = get_object_by_uuid(object_uuid)
    if metadata is None:
        logger.warning("Object metadata not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=f"Object not found for uuid='{object_uuid}'")
    response = to_object_metadata_response(metadata, storage_dir, get_3d_storage_dir())
    logger.debug(
        "Object metadata returned: uuid=%s session_id=%s object_id=%d",
        object_uuid,
        metadata.session_id,
        metadata.object_id,
    )
    return response


@router.get("/{uid}/objects", response_model=ObjectListResponse)
async def get_session_objects(uid: str) -> ObjectListResponse:
    """Return all processed objects for a session with cutout thumbnails.

    Scans the storage directory for finalized per-object cutout PNGs and
    returns them as base64 thumbnails alongside their tight alpha bounds and
    a flag indicating whether a GLB 3D model has been generated.
    """
    logger.debug("Objects list requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    obj_ids = list_object_ids(uid, visible_only=True)
    three_d_dir = get_3d_storage_dir()

    # TODO: this loop performs blocking I/O per object synchronously on the async event loop.
    # For MVP session sizes this is acceptable; move to a thread pool executor if sessions
    # grow to many large objects.
    objects_list: list[ObjectInfo] = []
    for oid in obj_ids:
        try:
            cutout_path = resolve_object_cutout_path(storage_dir, uid, oid)
            if not cutout_path.exists():
                logger.warning(
                    "Objects list: cutout missing for uid=%s object_id=%d path=%s — skipping",
                    uid,
                    oid,
                    cutout_path,
                )
                continue
            cutout_bytes = cutout_path.read_bytes()
            cutout_b64 = to_base64_ascii(cutout_bytes)
            cutout_bounds = extract_cutout_bounds_from_png_bytes(cutout_bytes)
            has_3d = resolve_object_glb_path(three_d_dir, uid, oid).exists()
            # Metadata is absent for objects created before it was introduced;
            # those fall back to nulls plus an unmoved (0, 0) offset.
            meta = load_object_metadata(uid, oid)
            objects_list.append(
                ObjectInfo(
                    object_id=oid,
                    uuid=meta.uuid if meta is not None else None,
                    name=meta.name if meta is not None else None,
                    average_depth=meta.average_depth if meta is not None else None,
                    source_elevation_deg=(
                        meta.source_elevation_deg if meta is not None else None
                    ),
                    cutout_b64=cutout_b64,
                    format="png",
                    cutout_bounds=cutout_bounds,
                    has_3d=has_3d,
                    offset_x=meta.offset_x if meta is not None else 0.0,
                    offset_y=meta.offset_y if meta is not None else 0.0,
                    display_scale=meta.display_scale if meta is not None else 1.0,
                    clone_root_uuid=meta.clone_root_uuid if meta is not None else None,
                )
            )
        except FileNotFoundError as exc:
            logger.warning(
                "Objects list: file not found for uid=%s object_id=%d error=%s — skipping",
                uid,
                oid,
                exc,
            )

    logger.debug("Objects list returned: uid=%s count=%d", uid, len(objects_list))
    return ObjectListResponse(uid=uid, objects=objects_list)


@router.get("/{uid}/cache", response_model=UidCacheStatusResponse)
async def get_uid_cache_status(uid: str) -> UidCacheStatusResponse:
    """Return which processed artifacts are cached on disk for the given UID."""
    logger.debug("Cache status requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    obj_ids = list_object_ids(uid, visible_only=True)

    # Derive cutout bounds from the latest (highest-id) object.
    latest_object_id = max(obj_ids) if obj_ids else None
    cutout_path_to_check = (
        resolve_object_cutout_path(storage_dir, uid, latest_object_id)
        if latest_object_id is not None
        else None
    )
    cutout_bounds = None
    if cutout_path_to_check is not None and cutout_path_to_check.exists():
        # Session restore should not need to re-run segmentation just to recover
        # drag bounds, so cache metadata derives from stored PNG on demand.
        cutout_bounds = extract_cutout_bounds_from_png_bytes(cutout_path_to_check.read_bytes())

    three_d_dir = get_3d_storage_dir()
    has_3d = any(
        resolve_object_glb_path(three_d_dir, uid, oid).exists() for oid in obj_ids
    )

    name = get_session_name(uid)
    try:
        history_flags = get_history_flags(uid)
    except SessionNotFoundError:
        history_flags = None
    status = UidCacheStatusResponse(
        uid=uid,
        name=name,
        has_background=current_background_path(storage_dir, uid).exists(),
        has_cutout=bool(obj_ids),
        has_3d=has_3d,
        can_undo=history_flags.can_undo if history_flags is not None else False,
        can_redo=history_flags.can_redo if history_flags is not None else False,
        cutout_bounds=cutout_bounds,
    )
    logger.debug(
        "Cache status: uid=%s background=%s cutout=%s 3d=%s",
        uid,
        status.has_background,
        status.has_cutout,
        status.has_3d,
    )
    return status


def _attachment_filename(raw: str) -> str:
    """Sanitize a client-supplied download label for Content-Disposition."""

    cleaned = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in raw.strip())
    base = cleaned[:80] or "background"
    return base if base.lower().endswith(".png") else f"{base}.png"


@router.get("/{uid}/background")
async def get_background(
    uid: str,
    download: bool = Query(False, description="When true, set Content-Disposition: attachment."),
    filename: str | None = Query(None, description="Suggested download filename (sanitized)."),
) -> FileResponse:
    """Serve the cached background PNG for the given UID."""
    logger.debug("Background requested: uid=%s download=%s", uid, download)
    path = current_background_path(get_image_storage_dir(), uid)
    if not path.exists():
        logger.warning("Background not found: uid=%s path=%s", uid, path)
        raise HTTPException(status_code=404, detail="Background not found")
    headers: dict[str, str] = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{_attachment_filename(filename or uid)}"'
    logger.debug("Background served: uid=%s path=%s", uid, path)
    return FileResponse(path, media_type="image/png", headers=headers)


@router.get("/{uid}/cutout")
async def get_cutout(uid: str) -> FileResponse:
    """Serve the cached cutout PNG for the given UID.

    Returns the latest (highest-id) object cutout for the session, falling back
    to the legacy ``{uid}_cutout.png`` file for sessions created before the
    numbered-object scheme was introduced.
    """
    logger.debug("Cutout requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    obj_ids = list_object_ids(uid, visible_only=True)
    if not obj_ids:
        logger.warning("Cutout not found: uid=%s (no object ids)", uid)
        raise HTTPException(status_code=404, detail="Cutout not found")
    path = resolve_object_cutout_path(storage_dir, uid, max(obj_ids))
    if not path.exists():
        logger.warning("Cutout not found: uid=%s path=%s", uid, path)
        raise HTTPException(status_code=404, detail="Cutout not found")
    logger.debug("Cutout served: uid=%s path=%s", uid, path)
    return FileResponse(path, media_type="image/png")


@router.get("/{uid}/original")
async def get_original_image(uid: str) -> FileResponse:
    """Serve the original uploaded image for the given UID."""
    logger.debug("Original image requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    try:
        path = get_image_path(uid, storage_dir)
    except FileNotFoundError:
        logger.warning("Original image not found: uid=%s", uid)
        raise HTTPException(status_code=404, detail="Original image not found")
    suffix = path.suffix.lower().lstrip(".")
    media_type = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
    logger.debug("Original image served: uid=%s path=%s", uid, path)
    return FileResponse(path, media_type=media_type)


@router.get("/{uid}/preview")
async def get_session_preview(uid: str) -> FileResponse:
    """Serve the dashboard thumbnail for the given UID.

    Written at upload time (a downscaled copy of the original) and
    overwritten by the frontend after each edit settles, so it always shows
    the room roughly as the user left it. Returns 404 when absent — callers
    (the dashboard card) fall back to a placeholder rather than treating this
    as an error.
    """
    logger.debug("Session preview requested: uid=%s", uid)
    path = session_preview_path(get_image_storage_dir(), uid)
    if not path.exists():
        logger.warning("Session preview not found: uid=%s path=%s", uid, path)
        raise HTTPException(status_code=404, detail="Preview not found")
    logger.debug("Session preview served: uid=%s path=%s", uid, path)
    return FileResponse(path, media_type="image/jpeg")


@router.post("/{uid}/preview", status_code=204)
async def save_session_preview(uid: str, request: SessionPreviewRequest) -> Response:
    """Store a client-composited dashboard thumbnail for the given UID.

    Called fire-and-forget from the frontend, debounced, after edits settle
    (see ``composeSessionPreview`` / ``saveSessionPreview`` in the React app).
    Does not call ``touch_session``: the mutation that triggered this preview
    already bumped ``last_changed`` well before the debounced capture runs,
    so the dashboard's cache-buster is already correct, and bumping it again
    here would spin an extra, pointless sync-check reconcile in the open
    workspace.
    """
    logger.debug("Session preview save requested: uid=%s", uid)
    if not is_session_registered(uid):
        logger.warning("Session preview save failed — unknown uid: %s", uid)
        raise HTTPException(status_code=404, detail=f"Session not found for uid='{uid}'")

    try:
        image_bytes = base64.b64decode(request.image_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        logger.warning("Session preview save rejected — invalid base64: uid=%s detail=%s", uid, exc)
        raise HTTPException(status_code=422, detail="image_b64 is not valid base64.") from exc

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("Session preview save rejected — not a valid image: uid=%s detail=%s", uid, exc)
        raise HTTPException(status_code=422, detail="image_b64 does not decode to a valid image.") from exc

    storage_dir = get_image_storage_dir()
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = session_preview_path(storage_dir, uid)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        tmp_path.write_bytes(image_bytes)
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.error("Session preview save failed: uid=%s error=%s", uid, exc)
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Preview save failed: {exc}") from exc

    logger.debug("Session preview saved: uid=%s path=%s size_bytes=%d", uid, path, len(image_bytes))
    return Response(status_code=204)
