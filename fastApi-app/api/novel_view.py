from __future__ import annotations

import base64
import logging

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException

from avroom_object_removal.ai_engines.novel_view import NovelViewFacade

from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.object_storage import object_novel_view_path, resolve_object_cutout_path
from schemas.image import NovelViewRequest, NovelViewResponse
from settings import get_image_storage_dir

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)

_facade: NovelViewFacade | None = None


def _get_facade() -> NovelViewFacade:
    global _facade
    if _facade is None:
        _facade = NovelViewFacade()
    return _facade


def _bgra_to_png_bytes(bgra: np.ndarray) -> bytes:
    """Encode a BGRA uint8 array as PNG bytes."""

    success, encoded = cv2.imencode(".png", bgra)
    if not success:
        raise RuntimeError("Failed to encode novel-view PNG")
    return encoded.tobytes()


@router.post("/novel-view")
async def synthesize_novel_view(request: NovelViewRequest) -> NovelViewResponse:
    """Synthesize a novel 2D view of an existing object cutout at a requested pose.

    The cutout must already exist from the normal segment → inpaint flow.
    Returns JSON with base64 PNG (not GLB).
    """
    logger.info(
        "novel-view called: uid=%s object_id=%d elevation=%.1f azimuth=%.1f "
        "rel_elevation=%.1f radius=%.1f seed=%d",
        request.uid,
        request.object_id,
        request.elevation_deg,
        request.azimuth_deg,
        request.relative_elevation_deg,
        request.radius,
        request.seed,
    )

    storage_dir = get_image_storage_dir()
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
        result_bgra = _get_facade().synthesize(
            cutout_path,
            elevation_deg=request.elevation_deg,
            azimuth_deg=request.azimuth_deg,
            relative_elevation_deg=request.relative_elevation_deg,
            radius=request.radius,
            seed=request.seed,
        )
    except Exception as exc:
        logger.exception("Novel view synthesis failed")
        raise HTTPException(
            status_code=500,
            detail=f"Novel view synthesis failed: {exc}",
        ) from exc

    png_bytes = _bgra_to_png_bytes(result_bgra)
    cutout_bounds = extract_cutout_bounds_from_png_bytes(png_bytes)

    cache_path = object_novel_view_path(
        storage_dir,
        request.uid,
        request.object_id,
        request.azimuth_deg,
        request.relative_elevation_deg,
    )
    cache_path.write_bytes(png_bytes)

    logger.info(
        "novel-view complete: uid=%s object_id=%d png_bytes=%d shape=%s saved=%s",
        request.uid,
        request.object_id,
        len(png_bytes),
        result_bgra.shape,
        cache_path,
    )

    return NovelViewResponse(
        uid=request.uid,
        object_id=request.object_id,
        image_b64=base64.b64encode(png_bytes).decode("ascii"),
        format="png",
        cutout_bounds=cutout_bounds,
        elevation_deg=request.elevation_deg,
        azimuth_deg=request.azimuth_deg,
        relative_elevation_deg=request.relative_elevation_deg,
        radius=request.radius,
        seed=request.seed,
    )
