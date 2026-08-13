from __future__ import annotations

"""Debug/test endpoints for visualizing raw pipeline stage output as images.

Not part of the production object-removal flow: no session, no storage
side effects. Upload a picture, get back a PNG showing what the depth model
or SAM's segment-everything mode produced. Gated by ``DEBUG_ENDPOINTS``
(default enabled) via :func:`settings.get_debug_endpoints_enabled`.
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from core.debug_vision import COLORMAPS, SEGMENT_SOURCES
from core.inference_pool.client import get_inference_client
from settings import get_debug_endpoints_enabled

router = APIRouter(prefix="/debug", tags=["debug"])
logger = logging.getLogger(__name__)

_DEFAULT_DEPTH_MODEL = "LiheYoung/depth-anything-small-hf"


def _require_enabled() -> None:
    if not get_debug_endpoints_enabled():
        raise HTTPException(status_code=404, detail="Debug endpoints are disabled.")


@router.post("/depth-map")
def debug_depth_map(
    file: Annotated[UploadFile, File(..., description="Image to depth-map.")],
    model: Annotated[str, Query(description="HF depth-estimation checkpoint name.")] = (
        _DEFAULT_DEPTH_MODEL
    ),
    colormap: Annotated[
        str, Query(description=f"One of {sorted(COLORMAPS)}.")
    ] = "none",
) -> Response:
    """Render a Depth-Anything depth map for an uploaded image as a viewable PNG.

    Test/debug tool: nothing is written to session storage. Blocking (plain
    ``def``) so FastAPI runs it on the thread pool rather than the event loop.
    """
    _require_enabled()

    logger.info(
        "debug/depth-map called: filename=%s model=%s colormap=%s",
        file.filename,
        model,
        colormap,
    )

    if colormap not in COLORMAPS:
        raise HTTPException(
            status_code=422, detail=f"Unknown colormap '{colormap}'. Valid: {sorted(COLORMAPS)}"
        )

    try:
        image_bytes = file.file.read()
    except Exception as exc:
        logger.exception("debug/depth-map read failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {exc}") from exc

    start = time.monotonic()
    try:
        png_bytes = get_inference_client().run_debug_depth_map(
            image_bytes=image_bytes, model_name=model, colormap=colormap
        )
    except ValueError as exc:
        logger.warning("debug/depth-map rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("debug/depth-map failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Depth-map generation failed: {exc}") from exc

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "debug/depth-map complete: filename=%s png_bytes=%d elapsed_ms=%.1f",
        file.filename,
        len(png_bytes),
        elapsed_ms,
    )

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"X-Elapsed-Ms": f"{elapsed_ms:.1f}"},
    )


@router.post("/sam-everything")
def debug_sam_everything(
    file: Annotated[UploadFile, File(..., description="Image to segment.")],
    source: Annotated[
        str, Query(description="'depth' (production-matching) or 'rgb' (raw photo).")
    ] = "depth",
    depth_model: Annotated[str, Query(description="Depth checkpoint used when source=depth.")] = (
        _DEFAULT_DEPTH_MODEL
    ),
    points_per_side: Annotated[int, Query(ge=4, le=64, description="SAM probe grid density.")] = 16,
    alpha: Annotated[float, Query(ge=0.0, le=1.0, description="Overlay tint strength.")] = 0.45,
) -> Response:
    """Render SAM's segment-everything output as a colored overlay on the photo.

    Test/debug tool: nothing is written to session storage. ``source=depth``
    (default) mirrors the production pipeline rule (SAM receives the depth
    map, not RGB); ``source=rgb`` demonstrates why that rule exists. Blocking
    (plain ``def``) so FastAPI runs it on the thread pool.
    """
    _require_enabled()

    logger.info(
        "debug/sam-everything called: filename=%s source=%s points_per_side=%d",
        file.filename,
        source,
        points_per_side,
    )

    if source not in SEGMENT_SOURCES:
        raise HTTPException(
            status_code=422, detail=f"Unknown source '{source}'. Valid: {sorted(SEGMENT_SOURCES)}"
        )

    try:
        image_bytes = file.file.read()
    except Exception as exc:
        logger.exception("debug/sam-everything read failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {exc}") from exc

    start = time.monotonic()
    try:
        png_bytes, mask_count = get_inference_client().run_debug_sam_everything(
            image_bytes=image_bytes,
            source=source,
            depth_model_name=depth_model,
            points_per_side=points_per_side,
            alpha=alpha,
        )
    except ValueError as exc:
        logger.warning("debug/sam-everything rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("debug/sam-everything failed: filename=%s", file.filename)
        raise HTTPException(
            status_code=500, detail=f"SAM segment-everything failed: {exc}"
        ) from exc

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "debug/sam-everything complete: filename=%s masks=%d png_bytes=%d elapsed_ms=%.1f",
        file.filename,
        mask_count,
        len(png_bytes),
        elapsed_ms,
    )

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"X-Mask-Count": str(mask_count), "X-Elapsed-Ms": f"{elapsed_ms:.1f}"},
    )
