from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Response

from avroom_object_removal.ai_engines.novel_view import NovelViewRotationAdapter

from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.inference_pool.client import get_inference_client
from core.object_storage import (
    object_glb_path,
    object_novel_view_path,
    object_novel_view_preview_path,
    resolve_object_cutout_path,
    resolve_object_glb_path,
)
from core.object_metadata import load_object_metadata
from schemas.image import NovelViewPreviewCacheRequest, NovelViewRequest, NovelViewResponse
from settings import get_3d_storage_dir, get_image_storage_dir, touch_session

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)

DEFAULT_SOURCE_ELEVATION_DEG = 15.0

# Angular granularity the HTTP layer quantizes poses to before touching the
# disk cache or the model. Synthesis is cached per (azimuth, relative
# elevation), so collapsing arbitrary user-dragged angles onto a coarse grid
# turns near-identical requests into cache hits instead of fresh (expensive)
# inference runs. This is an HTTP-layer concern only -- the adapter and the
# direct Python API keep accepting exact angles.
ROTATION_STEP_DEG = 10.0


def _ensure_object_glb(*, uid: str, object_id: int, cutout_path: Path) -> Path:
    """Return the on-disk GLB for ``(uid, object_id)``, generating it if missing.

    Looks up the cached mesh under the 3D storage dir first (including the
    legacy ``{uid}.glb`` name for object 0). On a miss, runs the existing 3D
    generation job and writes the canonical numbered path
    ``{uid}_{object_id}.glb``.
    """

    glb_dir = get_3d_storage_dir()
    glb_dir.mkdir(parents=True, exist_ok=True)
    existing = resolve_object_glb_path(glb_dir, uid, object_id)
    if existing.is_file() and existing.stat().st_size > 0:
        logger.info(
            "novel-view GLB cache hit: uid=%s object_id=%d path=%s",
            uid,
            object_id,
            existing,
        )
        return existing

    logger.info(
        "novel-view GLB cache miss; generating: uid=%s object_id=%d cutout=%s",
        uid,
        object_id,
        cutout_path,
    )
    try:
        glb_bytes = get_inference_client().run_generate_3d(cutout_path=cutout_path)
    except Exception as exc:
        logger.exception("novel-view GLB generation failed")
        raise HTTPException(
            status_code=500,
            detail=f"3D generation for novel-view failed: {exc}",
        ) from exc

    if not isinstance(glb_bytes, bytes) or not glb_bytes:
        logger.error("novel-view GLB generation returned empty bytes")
        raise HTTPException(
            status_code=500,
            detail="3D generation for novel-view returned empty GLB bytes",
        )

    out_path = object_glb_path(glb_dir, uid, object_id)
    out_path.write_bytes(glb_bytes)
    touch_session(uid)
    logger.info(
        "novel-view GLB written: uid=%s object_id=%d bytes=%d path=%s",
        uid,
        object_id,
        len(glb_bytes),
        out_path,
    )
    return out_path


def _bgra_to_png_bytes(bgra: np.ndarray) -> bytes:
    """Encode a BGRA uint8 array as PNG bytes."""

    success, encoded = cv2.imencode(".png", bgra)
    if not success:
        raise RuntimeError("Failed to encode novel-view PNG")
    return encoded.tobytes()


def _snap_to_step(value: float, step: float) -> float:
    """Round ``value`` onto the nearest multiple of ``step``.

    Returns ``0.0`` rather than ``-0.0`` so snapped values compare and format
    identically regardless of which side of zero they came from.
    """

    return round(value / step) * step + 0.0


def _normalize_azimuth_deg(azimuth_deg: float) -> float:
    """Wrap an azimuth into ``(-180, 180]``.

    Keeps equivalent rotations on a single representation (e.g. 355 and -5
    both resolve to -5) so they share one disk-cache entry.
    """

    wrapped = (azimuth_deg + 180.0) % 360.0 - 180.0
    if wrapped == -180.0:
        wrapped = 180.0
    return wrapped + 0.0


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
    object_meta = load_object_metadata(storage_dir, request.uid, request.object_id)
    source_elevation_deg = (
        object_meta.source_elevation_deg
        if object_meta is not None
        else DEFAULT_SOURCE_ELEVATION_DEG
    )
    if object_meta is not None and abs(request.elevation_deg - source_elevation_deg) > 1e-3:
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

    # Quantize onto a coarse grid so repeat/near-repeat poses share one cache
    # entry. Radius is a distance, not an angle, and is left unsnapped.
    snapped_azimuth_deg = _normalize_azimuth_deg(
        _snap_to_step(resolved_pose.azimuth_deg, ROTATION_STEP_DEG)
    )
    snapped_relative_elevation_deg = _snap_to_step(
        resolved_pose.relative_elevation_deg, ROTATION_STEP_DEG
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

    cache_path = object_novel_view_path(
        storage_dir,
        request.uid,
        request.object_id,
        snapped_azimuth_deg,
        snapped_relative_elevation_deg,
    )

    # A cache hit must be newer than the source cutout: rescale-by-depth
    # rewrites the cutout PNG in place, and a rotation cached against the
    # pre-rescale cutout is stale even though the filename still matches.
    cache_is_fresh = (
        cache_path.exists() and cache_path.stat().st_mtime >= cutout_path.stat().st_mtime
    )

    if cache_is_fresh:
        logger.info(
            "novel-view cache hit: uid=%s object_id=%d path=%s",
            request.uid,
            request.object_id,
            cache_path,
        )
        png_bytes = cache_path.read_bytes()
    else:
        try:
            glb_path = _ensure_object_glb(
                uid=request.uid,
                object_id=request.object_id,
                cutout_path=cutout_path,
            )
            result_bgra = get_inference_client().run_novel_view(
                cutout_path=cutout_path,
                elevation_deg=source_elevation_deg,
                azimuth_deg=snapped_azimuth_deg,
                relative_elevation_deg=snapped_relative_elevation_deg,
                radius=resolved_pose.radius,
                mesh_path=glb_path,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Novel view synthesis failed")
            raise HTTPException(
                status_code=500,
                detail=f"Novel view synthesis failed: {exc}",
            ) from exc

        png_bytes = _bgra_to_png_bytes(result_bgra)
        cache_path.write_bytes(png_bytes)
        touch_session(request.uid)

        logger.info(
            "novel-view complete: uid=%s object_id=%d png_bytes=%d shape=%s saved=%s",
            request.uid,
            request.object_id,
            len(png_bytes),
            result_bgra.shape,
            cache_path,
        )

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
        image_b64=base64.b64encode(png_bytes).decode("ascii"),
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
    snapped_azimuth_deg = _normalize_azimuth_deg(
        _snap_to_step(request.azimuth_deg, ROTATION_STEP_DEG)
    )
    snapped_relative_elevation_deg = _snap_to_step(
        request.relative_elevation_deg, ROTATION_STEP_DEG
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
