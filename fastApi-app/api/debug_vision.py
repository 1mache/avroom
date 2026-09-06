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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from core.auth.admin import require_admin
from core.debug_vision import COLORMAPS, DEPTH_STRATEGIES, NORMAL_HUB_MODELS, SEGMENT_SOURCES
from core.image_validation import ImageValidator
from core.inference_pool.client import InferenceJobError, get_inference_client
from schemas.debug import (
    DebugAutoMaskPickResponse,
    DebugCheckResult,
    DebugInpaintVerifyResponse,
    DebugValidationResponse,
)
from settings import get_debug_endpoints_enabled

router = APIRouter(prefix="/debug", tags=["debug"], dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)

_DEFAULT_DEPTH_MODEL = "LiheYoung/depth-anything-small-hf"
_DEFAULT_NORMAL_HUB_MODEL = "metric3d_vit_small"


def _require_enabled() -> None:
    if not get_debug_endpoints_enabled():
        raise HTTPException(status_code=404, detail="Debug endpoints are disabled.")


@router.post("/validate", response_model=DebugValidationResponse)
def debug_validate(
    file: Annotated[UploadFile, File(..., description="Image to validate.")],
) -> DebugValidationResponse:
    """Run the full upload-validation scoreboard on an image, with no side effects.

    Unlike ``POST /images/upload``, this never persists anything, never
    creates a session, and never stops at the first failed check — every
    technical check plus the content (CLIP) checks all run and are reported,
    regardless of pass/fail. Always returns 200; a failed check is data, not
    an error. Runs independently of ``VALIDATE`` (this endpoint *is* the
    validator). Blocking (plain ``def``) so FastAPI runs it on the thread pool.
    """
    _require_enabled()

    logger.info("debug/validate called: filename=%s content_type=%s", file.filename, file.content_type)

    try:
        file_bytes = file.file.read()
    except Exception as exc:
        logger.exception("debug/validate read failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {exc}") from exc

    start = time.monotonic()

    technical_results = ImageValidator().validate_all(
        file_bytes, filename=file.filename, content_type=file.content_type
    )
    technical = [
        DebugCheckResult(name=r.name, passed=r.passed, score=r.score, message=r.message)
        for r in technical_results
    ]
    technical_ok = all(r.passed for r in technical_results)
    decode_failed = any(r.name == "decode" and not r.passed for r in technical_results)

    content: list[DebugCheckResult] = []
    content_ok: bool | None = None
    content_skipped_reason: str | None = None

    if decode_failed:
        content_skipped_reason = "Technical validation could not decode the image."
        logger.info("debug/validate content stage skipped: decode failed")
    else:
        try:
            outcome = get_inference_client().run_validate_content(image_bytes=file_bytes)
        except Exception as exc:
            logger.exception("debug/validate content stage failed: filename=%s", file.filename)
            raise HTTPException(status_code=500, detail=f"Content validation failed: {exc}") from exc

        content_ok = outcome.is_valid
        # `checks` and `scores` use unrelated key namespaces (e.g.
        # "scene_space_or_landscape" vs "scene_p" in the CLIP strategy) with
        # no declared mapping between them, so scores aren't attached
        # per-check here — `scores` is a separate raw-metrics dict, not part
        # of this per-check report. `messages` has no check-name either, but
        # is appended in the same order the checks dict iterates failures, so
        # popping in order pairs each failed check with its message.
        messages_in_order = list(outcome.messages)
        content = [
            DebugCheckResult(
                name=name,
                passed=passed,
                score=None,
                message=messages_in_order.pop(0) if not passed and messages_in_order else "",
            )
            for name, passed in outcome.checks.items()
        ]

    elapsed_ms = (time.monotonic() - start) * 1000
    ok = technical_ok and (content_ok is not False)
    logger.info(
        "debug/validate complete: filename=%s technical_ok=%s content_ok=%s elapsed_ms=%.1f",
        file.filename,
        technical_ok,
        content_ok,
        elapsed_ms,
    )

    return DebugValidationResponse(
        ok=ok,
        technical_ok=technical_ok,
        content_ok=content_ok,
        technical=technical,
        content=content,
        content_skipped_reason=content_skipped_reason,
        elapsed_ms=elapsed_ms,
    )


@router.post("/depth-map")
def debug_depth_map(
    file: Annotated[UploadFile, File(..., description="Image to depth-map.")],
    model: Annotated[
        str, Query(description="HF depth-estimation checkpoint name. Only used when strategy=anything.")
    ] = (_DEFAULT_DEPTH_MODEL),
    colormap: Annotated[
        str, Query(description=f"One of {sorted(COLORMAPS)}.")
    ] = "none",
    strategy: Annotated[
        str,
        Query(
            description=(
                f"One of {sorted(DEPTH_STRATEGIES)}. 'anything' is a single checkpoint "
                "(honors 'model'); 'blended' and 'enhanced_edge' are the multi-checkpoint "
                "strategies production actually uses."
            )
        ),
    ] = "anything",
) -> Response:
    """Render a depth map for an uploaded image as a viewable PNG.

    Test/debug tool: nothing is written to session storage. Blocking (plain
    ``def``) so FastAPI runs it on the thread pool rather than the event loop.
    """
    _require_enabled()

    logger.info(
        "debug/depth-map called: filename=%s model=%s colormap=%s strategy=%s",
        file.filename,
        model,
        colormap,
        strategy,
    )

    if colormap not in COLORMAPS:
        raise HTTPException(
            status_code=422, detail=f"Unknown colormap '{colormap}'. Valid: {sorted(COLORMAPS)}"
        )
    if strategy not in DEPTH_STRATEGIES:
        raise HTTPException(
            status_code=422, detail=f"Unknown strategy '{strategy}'. Valid: {sorted(DEPTH_STRATEGIES)}"
        )

    try:
        image_bytes = file.file.read()
    except Exception as exc:
        logger.exception("debug/depth-map read failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {exc}") from exc

    start = time.monotonic()
    try:
        png_bytes = get_inference_client().run_debug_depth_map(
            image_bytes=image_bytes, model_name=model, colormap=colormap, strategy=strategy
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


@router.post("/normal-map")
def debug_normal_map(
    file: Annotated[UploadFile, File(..., description="Image to estimate normals for.")],
    hub_model: Annotated[
        str,
        Query(
            description=(
                f"Metric3D torch.hub entrypoint. One of {sorted(NORMAL_HUB_MODELS)}. "
                "ViT models only (ConvNeXt hubs have no normals)."
            )
        ),
    ] = _DEFAULT_NORMAL_HUB_MODEL,
) -> Response:
    """Render a surface-normal map for an uploaded image as a viewable PNG.

    Test/debug tool: nothing is written to session storage. Blocking (plain
    ``def``) so FastAPI runs it on the thread pool rather than the event loop.
    """
    _require_enabled()

    logger.info(
        "debug/normal-map called: filename=%s hub_model=%s",
        file.filename,
        hub_model,
    )

    if hub_model not in NORMAL_HUB_MODELS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown hub_model '{hub_model}'. Valid: {sorted(NORMAL_HUB_MODELS)}",
        )

    try:
        image_bytes = file.file.read()
    except Exception as exc:
        logger.exception("debug/normal-map read failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {exc}") from exc

    start = time.monotonic()
    try:
        png_bytes = get_inference_client().run_debug_normal_map(
            image_bytes=image_bytes, hub_model=hub_model
        )
    except ValueError as exc:
        logger.warning("debug/normal-map rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("debug/normal-map failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Normal-map generation failed: {exc}") from exc

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "debug/normal-map complete: filename=%s png_bytes=%d elapsed_ms=%.1f",
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
    depth_strategy: Annotated[
        str,
        Query(description=f"Depth strategy used when source=depth. One of {sorted(DEPTH_STRATEGIES)}."),
    ] = "anything",
    pred_iou_thresh: Annotated[
        float, Query(ge=0.0, le=1.0, description="Minimum predicted mask-quality IoU to keep a candidate.")
    ] = 0.88,
    stability_score_thresh: Annotated[
        float, Query(ge=0.0, le=1.0, description="Minimum stability score to keep a candidate.")
    ] = 0.95,
    min_mask_region_area: Annotated[
        int, Query(ge=0, le=100_000, description="Discard connected components smaller than this many pixels.")
    ] = 0,
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
    if depth_strategy not in DEPTH_STRATEGIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown depth_strategy '{depth_strategy}'. Valid: {sorted(DEPTH_STRATEGIES)}",
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
            depth_strategy=depth_strategy,
            pred_iou_thresh=pred_iou_thresh,
            stability_score_thresh=stability_score_thresh,
            min_mask_region_area=min_mask_region_area,
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


def _read_upload(file: UploadFile, *, label: str) -> bytes:
    try:
        return file.file.read()
    except Exception as exc:
        logger.exception("%s read failed: filename=%s", label, file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {exc}") from exc


_MAX_DEBUG_SEEDS = 8


def _http_from_inference(exc: InferenceJobError) -> HTTPException:
    detail = str(exc)
    lowered = detail.lower()
    if (
        "outside the image" in lowered
        or "no viable mask" in lowered
        or "out of range" in lowered
        or "at most" in lowered
        or "must match" in lowered
        or "invalid points" in lowered
    ):
        return HTTPException(status_code=422, detail=detail)
    return HTTPException(status_code=500, detail=detail)


def _parse_extra_point_strings(raw_points: list[str] | None) -> tuple[tuple[int, int], ...]:
    """Parse repeated ``points=x,y`` query values into integer pairs.

    These are *extra* seeds beyond the primary ``x``, ``y`` — at most 7 so the
    full prompt stays within ``_MAX_DEBUG_SEEDS``.
    """
    if not raw_points:
        return ()
    if len(raw_points) > _MAX_DEBUG_SEEDS - 1:
        raise ValueError(f"At most {_MAX_DEBUG_SEEDS} seeds are allowed.")
    parsed: list[tuple[int, int]] = []
    for raw in raw_points:
        parts = raw.split(",")
        if len(parts) != 2:
            raise ValueError(f"Invalid points value {raw!r}; expected 'x,y'.")
        try:
            parsed.append((int(parts[0].strip()), int(parts[1].strip())))
        except ValueError as exc:
            raise ValueError(f"Invalid points value {raw!r}; expected 'x,y'.") from exc
    return tuple(parsed)


def _seed_points_for_request(
    x: int, y: int, raw_points: list[str] | None
) -> tuple[tuple[int, int], ...]:
    extras = _parse_extra_point_strings(raw_points)
    return ((x, y),) + extras


@router.post("/auto-mask-pick", response_model=DebugAutoMaskPickResponse)
def debug_auto_mask_pick(
    file: Annotated[UploadFile, File(..., description="Image to segment.")],
    x: Annotated[int, Query(description="Primary click x in natural image pixels.")],
    y: Annotated[int, Query(description="Primary click y in natural image pixels.")],
    points: Annotated[
        list[str] | None,
        Query(
            description=(
                "Optional extra seeds as repeated 'x,y' query values "
                "(max 7 extras; 8 total including primary)."
            ),
        ),
    ] = None,
) -> DebugAutoMaskPickResponse:
    """Rank every SAM candidate at a click with CLIP. No session writes."""
    _require_enabled()
    try:
        seed_points = _seed_points_for_request(x, y, points)
    except ValueError as exc:
        logger.warning("debug/auto-mask-pick rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info(
        "debug/auto-mask-pick called: filename=%s click=(%d,%d) seeds=%d",
        file.filename,
        x,
        y,
        len(seed_points),
    )
    image_bytes = _read_upload(file, label="debug/auto-mask-pick")
    try:
        payload = get_inference_client().run_debug_auto_mask_pick(
            image_bytes=image_bytes, x=x, y=y, points=seed_points
        )
    except InferenceJobError as exc:
        logger.warning("debug/auto-mask-pick rejected: %s", exc)
        raise _http_from_inference(exc) from exc
    except ValueError as exc:
        logger.warning("debug/auto-mask-pick rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("debug/auto-mask-pick failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Auto mask pick failed: {exc}") from exc

    logger.info(
        "debug/auto-mask-pick complete: filename=%s candidates=%d winner=%s",
        file.filename,
        len(payload["candidates"]),
        payload["winner_index"],
    )
    return DebugAutoMaskPickResponse.model_validate(payload)


@router.post("/inpaint-verify", response_model=DebugInpaintVerifyResponse)
def debug_inpaint_verify(
    file: Annotated[UploadFile, File(..., description="Image to inpaint.")],
    x: Annotated[int, Query(description="Primary click x in natural image pixels.")],
    y: Annotated[int, Query(description="Primary click y in natural image pixels.")],
    mask_index: Annotated[
        int | None,
        Query(description="Candidate index to inpaint. Defaults to CLIP winner."),
    ] = None,
    points: Annotated[
        list[str] | None,
        Query(
            description=(
                "Optional extra seeds as repeated 'x,y' query values "
                "(max 7 extras; 8 total including primary)."
            ),
        ),
    ] = None,
) -> DebugInpaintVerifyResponse:
    """Run hybrid inpaint + CLIP retries on one mask. No session writes."""
    _require_enabled()
    try:
        seed_points = _seed_points_for_request(x, y, points)
    except ValueError as exc:
        logger.warning("debug/inpaint-verify rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info(
        "debug/inpaint-verify called: filename=%s click=(%d,%d) seeds=%d mask_index=%s",
        file.filename,
        x,
        y,
        len(seed_points),
        mask_index,
    )
    image_bytes = _read_upload(file, label="debug/inpaint-verify")
    try:
        payload = get_inference_client().run_debug_inpaint_verify(
            image_bytes=image_bytes,
            x=x,
            y=y,
            mask_index=mask_index,
            points=seed_points,
        )
    except InferenceJobError as exc:
        logger.warning("debug/inpaint-verify rejected: %s", exc)
        raise _http_from_inference(exc) from exc
    except ValueError as exc:
        logger.warning("debug/inpaint-verify rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("debug/inpaint-verify failed: filename=%s", file.filename)
        raise HTTPException(status_code=500, detail=f"Inpaint verify failed: {exc}") from exc

    logger.info(
        "debug/inpaint-verify complete: filename=%s mask_index=%s passed=%s attempts=%d",
        file.filename,
        payload["mask_index"],
        payload["passed"],
        len(payload["attempts"]),
    )
    return DebugInpaintVerifyResponse.model_validate(payload)
