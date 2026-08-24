from __future__ import annotations

import base64
import binascii
import logging

from fastapi import APIRouter, HTTPException, Response

from avroom_object_removal.ai_engines.novel_view import NovelViewRotationAdapter

from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.image_codec import to_base64_ascii
from core.novel_view_cache import ensure_novel_view_png
from core.object_storage import (
    object_novel_view_preview_path,
    resolve_object_cutout_path,
)
from core.object_metadata import load_object_metadata
from schemas.common import DEFAULT_SOURCE_ELEVATION_DEG
from schemas.novel_view import (
    NovelViewPreviewCacheRequest,
    NovelViewRequest,
    NovelViewResponse,
)
from settings import get_image_storage_dir

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)

# Angular granularity the HTTP layer quantizes poses to before touching the
# disk cache or the model. Synthesis is cached per (azimuth, relative
# elevation), so collapsing arbitrary user-dragged angles onto a coarse grid
# turns near-identical requests into cache hits instead of fresh (expensive)
# inference runs. This is an HTTP-layer concern only -- the adapter and the
# direct Python API keep accepting exact angles.
ROTATION_STEP_DEG = 10.0

# Below this the requested and stored elevations are the same angle, just
# rounded differently on the way through JSON — not worth a log line.
_ELEVATION_MATCH_TOLERANCE_DEG = 1e-3


def _without_negative_zero(value: float) -> float:
    """Return ``0.0`` in place of ``-0.0`` so cache filenames never differ by sign."""

    return value + 0.0


def _snap_to_step(value: float, step: float) -> float:
    """Round ``value`` onto the nearest multiple of ``step``."""

    return _without_negative_zero(round(value / step) * step)


def _normalize_azimuth_deg(azimuth_deg: float) -> float:
    """Wrap an azimuth into ``(-180, 180]``.

    Keeps equivalent rotations on a single representation (e.g. 355 and -5
    both resolve to -5) so they share one disk-cache entry.
    """

    wrapped = (azimuth_deg + 180.0) % 360.0 - 180.0
    if wrapped == -180.0:
        wrapped = 180.0
    return _without_negative_zero(wrapped)


def _snap_pose(azimuth_deg: float, relative_elevation_deg: float) -> tuple[float, float]:
    """Quantize a pose onto the disk-cache grid.

    Both routes cache on this snapped pose, so repeat/near-repeat requests
    share one entry instead of each user-dragged angle minting a fresh
    (expensive) synthesis.
    """

    snapped_azimuth_deg = _normalize_azimuth_deg(_snap_to_step(azimuth_deg, ROTATION_STEP_DEG))
    snapped_relative_elevation_deg = _snap_to_step(relative_elevation_deg, ROTATION_STEP_DEG)
    return snapped_azimuth_deg, snapped_relative_elevation_deg


@router.post("/novel-view")
def synthesize_novel_view(request: NovelViewRequest) -> NovelViewResponse:
    """Synthesize a novel 2D view of an existing object cutout at a requested pose.

    The cutout must already exist from the normal segment → inpaint flow.
    Returns JSON with base64 PNG (not GLB).
    """
    logger.info(
        "novel-view called: uid=%s object_id=%d elevation=%.1f azimuth=%.1f "
        "azimuth_dir=%s rel_elevation=%.1f elevation_dir=%s radius=%.1f zoom_dir=%s",
        request.uid,
        request.object_id,
        request.elevation_deg,
        request.azimuth_deg,
        request.azimuth_direction,
        request.relative_elevation_deg,
        request.elevation_direction,
        request.radius,
        request.zoom_direction,
    )

    storage_dir = get_image_storage_dir()
    object_meta = load_object_metadata(request.uid, request.object_id)
    source_elevation_deg = (
        object_meta.source_elevation_deg
        if object_meta is not None
        else DEFAULT_SOURCE_ELEVATION_DEG
    )
    if object_meta is not None and abs(request.elevation_deg - source_elevation_deg) > _ELEVATION_MATCH_TOLERANCE_DEG:
        logger.info(
            "novel-view overriding request elevation %.1f with stored source elevation %.1f",
            request.elevation_deg,
            source_elevation_deg,
        )

    try:
        resolved_pose = NovelViewRotationAdapter.resolve_pose(
            azimuth_deg=request.azimuth_deg,
            relative_elevation_deg=request.relative_elevation_deg,
            radius=request.radius,
            azimuth_direction=request.azimuth_direction,
            elevation_direction=request.elevation_direction,
            zoom_direction=request.zoom_direction,
        )
    except ValueError as exc:
        logger.error("Invalid novel-view pose: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Radius is a distance, not an angle, and is left unsnapped.
    snapped_azimuth_deg, snapped_relative_elevation_deg = _snap_pose(
        resolved_pose.azimuth_deg, resolved_pose.relative_elevation_deg
    )

    logger.info(
        "novel-view resolved pose: azimuth=%.1f rel_elevation=%.1f radius=%.1f "
        "(snapped azimuth=%.1f rel_elevation=%.1f)",
        resolved_pose.azimuth_deg,
        resolved_pose.relative_elevation_deg,
        resolved_pose.radius,
        snapped_azimuth_deg,
        snapped_relative_elevation_deg,
    )

    cutout_path = resolve_object_cutout_path(storage_dir, request.uid, request.object_id)
    if not cutout_path.exists():
        logger.error(
            "Cutout image not found: uid=%s object_id=%d path=%s",
            request.uid,
            request.object_id,
            cutout_path,
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"Cutout image not found at {cutout_path}. "
                f"Run object removal / inpaint first so the cutout for object "
                f"{request.object_id} exists."
            ),
        )

    try:
        png_bytes = ensure_novel_view_png(
            uid=request.uid,
            object_id=request.object_id,
            cutout_path=cutout_path,
            azimuth_deg=snapped_azimuth_deg,
            relative_elevation_deg=snapped_relative_elevation_deg,
            elevation_deg=source_elevation_deg,
            radius=resolved_pose.radius,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Novel view synthesis failed")
        raise HTTPException(
            status_code=500,
            detail=f"Novel view synthesis failed: {exc}",
        ) from exc

    # A confirmed real result (cached or freshly synthesized) for this exact
    # snapped pose makes any client-side preview placeholder obsolete.
    preview_path = object_novel_view_preview_path(
        storage_dir,
        request.uid,
        request.object_id,
        snapped_azimuth_deg,
        snapped_relative_elevation_deg,
    )
    if preview_path.exists():
        try:
            preview_path.unlink()
        except OSError:
            logger.warning("Failed to remove stale novel-view preview: path=%s", preview_path)

    cutout_bounds = extract_cutout_bounds_from_png_bytes(png_bytes)

    return NovelViewResponse(
        uid=request.uid,
        object_id=request.object_id,
        image_b64=to_base64_ascii(png_bytes),
        format="png",
        cutout_bounds=cutout_bounds,
        elevation_deg=source_elevation_deg,
        azimuth_deg=snapped_azimuth_deg,
        azimuth_direction=request.azimuth_direction,
        relative_elevation_deg=snapped_relative_elevation_deg,
        elevation_direction=request.elevation_direction,
        radius=resolved_pose.radius,
        zoom_direction=request.zoom_direction,
    )


@router.post("/novel-view/preview-cache", status_code=204)
def cache_novel_view_preview(request: NovelViewPreviewCacheRequest) -> Response:
    """Persist a client-rendered rotation preview as a best-effort placeholder.

    Called fire-and-forget from the frontend right when a rotation is
    committed, in parallel with the real (much slower) POST /images/novel-view
    request for the same pose. Written to a distinct ``*.preview.png`` path so
    the real endpoint's own cache-hit check can never mistake this for a
    genuine synthesis result -- that endpoint deletes the matching preview
    file once a real result for the same snapped pose is confirmed. If
    synthesis never completes (error, dropped request), the preview file is
    simply left in place as a fallback artifact.
    """
    snapped_azimuth_deg, snapped_relative_elevation_deg = _snap_pose(
        request.azimuth_deg, request.relative_elevation_deg
    )

    try:
        png_bytes = base64.b64decode(request.image_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        logger.error("Invalid novel-view preview payload: %s", exc)
        raise HTTPException(status_code=422, detail="image_b64 is not valid base64.") from exc

    preview_path = object_novel_view_preview_path(
        get_image_storage_dir(),
        request.uid,
        request.object_id,
        snapped_azimuth_deg,
        snapped_relative_elevation_deg,
    )
    preview_path.write_bytes(png_bytes)

    logger.info(
        "novel-view preview cached: uid=%s object_id=%d path=%s",
        request.uid,
        request.object_id,
        preview_path,
    )
    return Response(status_code=204)
