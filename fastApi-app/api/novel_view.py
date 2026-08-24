from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from avroom_object_removal.ai_engines.novel_view import NovelViewRotationAdapter

from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.image_codec import encode_png, to_base64_ascii
from core.inference_pool.client import get_inference_client
from core.object_3d import ensure_object_glb
from core.object_storage import resolve_object_cutout_path
from core.object_metadata import load_object_metadata
from schemas.common import DEFAULT_SOURCE_ELEVATION_DEG
from schemas.novel_view import NovelViewRequest, NovelViewResponse
from settings import get_image_storage_dir

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)

# Below this the requested and stored elevations are the same angle, just
# rounded differently on the way through JSON — not worth a log line.
_ELEVATION_MATCH_TOLERANCE_DEG = 1e-3


@router.post("/novel-view")
def synthesize_novel_view(request: NovelViewRequest) -> NovelViewResponse:
    """Synthesize a novel 2D view of an existing object cutout at a requested pose.

    The cutout must already exist from the normal segment → inpaint flow.
    Renders fresh from the object's GLB every call -- MeshRenderNovelViewStrategy
    is a direct mesh render, cheap enough that there is nothing worth caching
    per angle. Returns JSON with base64 PNG (not GLB).
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

    logger.info(
        "novel-view resolved pose: azimuth=%.1f rel_elevation=%.1f radius=%.1f",
        resolved_pose.azimuth_deg,
        resolved_pose.relative_elevation_deg,
        resolved_pose.radius,
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
        glb_path = ensure_object_glb(
            uid=request.uid, object_id=request.object_id, cutout_path=cutout_path
        )
        result_bgra = get_inference_client().run_novel_view(
            cutout_path=cutout_path,
            elevation_deg=source_elevation_deg,
            azimuth_deg=resolved_pose.azimuth_deg,
            relative_elevation_deg=resolved_pose.relative_elevation_deg,
            radius=resolved_pose.radius,
            mesh_path=glb_path,
        )
        png_bytes = encode_png(result_bgra, "novel-view")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Novel view synthesis failed")
        raise HTTPException(
            status_code=500,
            detail=f"Novel view synthesis failed: {exc}",
        ) from exc

    logger.info(
        "novel-view synthesized: uid=%s object_id=%d png_bytes=%d shape=%s",
        request.uid,
        request.object_id,
        len(png_bytes),
        result_bgra.shape,
    )

    cutout_bounds = extract_cutout_bounds_from_png_bytes(png_bytes)

    return NovelViewResponse(
        uid=request.uid,
        object_id=request.object_id,
        image_b64=to_base64_ascii(png_bytes),
        format="png",
        cutout_bounds=cutout_bounds,
        elevation_deg=source_elevation_deg,
        azimuth_deg=resolved_pose.azimuth_deg,
        azimuth_direction=request.azimuth_direction,
        relative_elevation_deg=resolved_pose.relative_elevation_deg,
        elevation_direction=request.elevation_direction,
        radius=resolved_pose.radius,
        zoom_direction=request.zoom_direction,
    )
