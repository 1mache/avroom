from __future__ import annotations

"""Pipeline functions backing the /debug visualization endpoints.

These are test/inspection tools, not part of the production object-removal
flow: they decode an arbitrary uploaded image, run one pipeline stage
(Depth-Anything or SAM segment-everything), render the result as a viewable
PNG, and return bytes. Nothing is persisted to session storage.
"""

import logging
import time
from typing import Any

import cv2
import numpy as np

from core.avroom_package import load_avroom_attr
from core.depth_cache import memory_image_key
from core.image_codec import encode_png, to_base64_ascii
from core.image_processing import _get_cutout_clip_scorer

logger = logging.getLogger(__name__)

# cv2.COLORMAP_* constants are ints; keep the name->id mapping here so the API
# layer can validate a query param without importing cv2 constants directly.
COLORMAPS: dict[str, int | None] = {
    "none": None,
    "inferno": cv2.COLORMAP_INFERNO,
    "magma": cv2.COLORMAP_MAGMA,
    "turbo": cv2.COLORMAP_TURBO,
    "jet": cv2.COLORMAP_JET,
}

SEGMENT_SOURCES = frozenset({"depth", "rgb"})

# Depth strategies selectable from the debug endpoints. "anything" is a single
# checkpoint (the only one that honors `model_name`); "blended" and
# "enhanced_edge" are the multi-checkpoint strategies production actually
# uses (see CLAUDE.md "AI Pipeline Architecture") — both construct with no
# required args.
DEPTH_STRATEGIES = frozenset({"anything", "blended", "enhanced_edge"})


def _decode_bgr(image_bytes: bytes, *, label: str) -> np.ndarray:
    """Decode raw upload bytes into a BGR uint8 array, or raise ``ValueError``."""
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        logger.error("Failed to decode %s image bytes (%d bytes)", label, len(image_bytes))
        raise ValueError(f"Could not decode {label} image bytes.")
    return decoded


def _build_depth_strategy(strategy: str, model_name: str) -> Any:
    """Construct a depth-mapping strategy by debug-endpoint selector name.

    ``model_name`` only applies to ``"anything"`` (the single-checkpoint
    strategy); it is ignored for the multi-checkpoint strategies.
    """
    if strategy not in DEPTH_STRATEGIES:
        raise ValueError(f"Unknown depth strategy '{strategy}'. Valid options: {sorted(DEPTH_STRATEGIES)}")

    if strategy == "anything":
        DepthAnythingMappingStrategy = load_avroom_attr(
            "DepthAnythingMappingStrategy", module="avroom_object_removal.ai_engines.depth"
        )
        return DepthAnythingMappingStrategy(model_name=model_name)

    if strategy == "blended":
        NearFarBlendedDepthMappingStrategy = load_avroom_attr(
            "NearFarBlendedDepthMappingStrategy", module="avroom_object_removal.ai_engines.depth"
        )
        return NearFarBlendedDepthMappingStrategy()

    EnhancedEdgeDepthMappingStrategy = load_avroom_attr(
        "EnhancedEdgeDepthMappingStrategy", module="avroom_object_removal.ai_engines.depth"
    )
    return EnhancedEdgeDepthMappingStrategy()


def render_depth_map_png(
    image_bytes: bytes, *, model_name: str, colormap: str, strategy: str = "anything"
) -> bytes:
    """Run a depth-mapping strategy on ``image_bytes`` and return a viewable depth-map PNG.

    Args:
        image_bytes: Raw uploaded image bytes (any format OpenCV can decode).
        model_name: HF checkpoint name; only used when ``strategy == "anything"``.
        colormap: Key into :data:`COLORMAPS`; ``"none"`` renders grayscale.
        strategy: Key into :data:`DEPTH_STRATEGIES`.

    Raises:
        ValueError: If the image bytes can't be decoded, or ``colormap``/``strategy`` is unknown.
    """
    if colormap not in COLORMAPS:
        raise ValueError(f"Unknown colormap '{colormap}'. Valid options: {sorted(COLORMAPS)}")

    logger.info(
        "Depth-map debug render starting: strategy=%s model=%s colormap=%s",
        strategy,
        model_name,
        colormap,
    )
    start = time.monotonic()

    bgr = _decode_bgr(image_bytes, label="depth-map")
    logger.debug("Decoded input image: shape=%s", bgr.shape)

    colorize_depth = load_avroom_attr("colorize_depth", module="avroom_object_removal.utils")

    depth_strategy = _build_depth_strategy(strategy, model_name)
    depth = depth_strategy.map_depth(bgr)
    logger.debug("Depth map computed: shape=%s dtype=%s", depth.shape, depth.dtype)

    rendered = colorize_depth(depth, colormap=COLORMAPS[colormap])
    png_bytes = encode_png(rendered, "depth-map debug")

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "Depth-map debug render complete: model=%s elapsed_ms=%.1f png_bytes=%d",
        model_name,
        elapsed_ms,
        len(png_bytes),
    )
    return png_bytes


def render_sam_everything_png(
    image_bytes: bytes,
    *,
    source: str,
    depth_model_name: str,
    points_per_side: int,
    alpha: float,
    depth_strategy: str = "anything",
    pred_iou_thresh: float = 0.88,
    stability_score_thresh: float = 0.95,
    min_mask_region_area: int = 0,
) -> tuple[bytes, int]:
    """Run SAM's segment-everything mode on ``image_bytes`` and render an overlay PNG.

    Args:
        image_bytes: Raw uploaded image bytes.
        source: ``"depth"`` feeds SAM the adapted Depth-Anything map (matches
            the production pipeline's rule); ``"rgb"`` feeds SAM the raw photo
            (for comparison — over-segments on fabric creases/shadows).
        depth_model_name: HF checkpoint used when ``source == "depth"`` and
            ``depth_strategy == "anything"``.
        points_per_side: SAM automatic-mask-generator probe grid density.
        alpha: Overlay tint strength, forwarded to ``overlay_masks``.
        depth_strategy: Key into :data:`DEPTH_STRATEGIES`; only used when
            ``source == "depth"``.
        pred_iou_thresh: Forwarded to ``predict_everything``.
        stability_score_thresh: Forwarded to ``predict_everything``.
        min_mask_region_area: Forwarded to ``predict_everything``.

    Returns:
        ``(png_bytes, mask_count)``. The overlay is always drawn on the
        original photo, regardless of ``source``.

    Raises:
        ValueError: If the image bytes can't be decoded, or ``source``/``depth_strategy`` is unknown.
    """
    if source not in SEGMENT_SOURCES:
        raise ValueError(f"Unknown source '{source}'. Valid options: {sorted(SEGMENT_SOURCES)}")

    logger.info(
        "SAM segment-everything debug render starting: source=%s points_per_side=%d",
        source,
        points_per_side,
    )
    start = time.monotonic()

    bgr = _decode_bgr(image_bytes, label="sam-everything")
    logger.debug("Decoded input image: shape=%s", bgr.shape)

    SamSegmentationStrategy = load_avroom_attr(
        "SamSegmentationStrategy",
        module="avroom_object_removal.ai_engines.segmentation.strategies",
    )
    SamImageAdapter = load_avroom_attr(
        "SamImageAdapter", module="avroom_object_removal.ai_engines.segmentation"
    )
    overlay_masks = load_avroom_attr("overlay_masks", module="avroom_object_removal.utils")

    if source == "depth":
        depth = _build_depth_strategy(depth_strategy, depth_model_name).map_depth(bgr)
        sam_input: np.ndarray = SamImageAdapter().get_adapted_image(
            depth, image_id="debug", point=(0, 0)
        )
        logger.debug("SAM input adapted from depth map: shape=%s", sam_input.shape)
    else:
        sam_input = bgr
        logger.debug("SAM input is raw RGB/BGR image: shape=%s", sam_input.shape)

    sam_strategy: Any = SamSegmentationStrategy()
    masks = sam_strategy.predict_everything(
        sam_input,
        points_per_side=points_per_side,
        pred_iou_thresh=pred_iou_thresh,
        stability_score_thresh=stability_score_thresh,
        min_mask_region_area=min_mask_region_area,
    )
    logger.info("SAM segment-everything found %d masks", len(masks))

    rendered = overlay_masks(bgr, masks, alpha=alpha, draw_outlines=True)
    png_bytes = encode_png(rendered, "sam-everything debug")

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "SAM segment-everything debug render complete: source=%s masks=%d elapsed_ms=%.1f png_bytes=%d",
        source,
        len(masks),
        elapsed_ms,
        len(png_bytes),
    )
    return png_bytes, len(masks)


def _png_b64(image: np.ndarray, label: str) -> str:
    return to_base64_ascii(encode_png(image, label))


def _validate_click(bgr: np.ndarray, x: int, y: int) -> None:
    height, width = bgr.shape[:2]
    if x < 0 or y < 0 or x >= width or y >= height:
        raise ValueError(f"Click ({x}, {y}) is outside the image ({width}x{height}).")


def _segment_click(
    image_bytes: bytes, bgr: np.ndarray, x: int, y: int
) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    ObjectSegmentor = load_avroom_attr("ObjectSegmentor")
    segmentor = ObjectSegmentor()
    return segmentor.get_mask_for_object_at_position(
        image_path=memory_image_key(image_bytes),
        x=x,
        y=y,
        image_bytes=image_bytes,
    )


def run_auto_mask_pick(image_bytes: bytes, *, x: int, y: int) -> dict[str, Any]:
    """Segment at a click and rank cutouts with CLIP. Returns JSON-ready dict."""
    start = time.monotonic()
    bgr = _decode_bgr(image_bytes, label="auto-mask-pick")
    _validate_click(bgr, x, y)

    select_best_cutout = load_avroom_attr("select_best_cutout")
    DEFAULT_THRESHOLD = load_avroom_attr(
        "DEFAULT_THRESHOLD", module="avroom_object_removal.core.cutout_selector"
    )
    _cutout_preview_bgr = load_avroom_attr(
        "_cutout_preview_bgr", module="avroom_object_removal.core.cutout_selector"
    )
    _crop_on_gray = load_avroom_attr(
        "_crop_on_gray", module="avroom_object_removal.core.cutout_selector"
    )
    _pil_rgb_to_bgr = load_avroom_attr(
        "_pil_rgb_to_bgr", module="avroom_object_removal.core.cutout_selector"
    )

    pairs = _segment_click(image_bytes, bgr, x, y)
    cutouts = [cutout for _mask, cutout in pairs]
    selection = select_best_cutout(
        cutouts,
        click_xy=(x, y),
        scorer=_get_cutout_clip_scorer(),
    )

    candidates: list[dict[str, Any]] = []
    for index, cutout in enumerate(cutouts):
        crop_pil = _crop_on_gray(cutout)
        clip_b64 = (
            _png_b64(_pil_rgb_to_bgr(crop_pil), f"clip crop {index}") if crop_pil is not None else None
        )
        reason = selection.reasons[index] if index < len(selection.reasons) else "unknown"
        score = float(selection.scores[index]) if index < len(selection.scores) else 0.0
        candidates.append(
            {
                "index": index,
                "score": round(score, 4),
                "reason": reason,
                "preview_b64": _png_b64(_cutout_preview_bgr(cutout, (x, y)), f"preview {index}"),
                "clip_crop_b64": clip_b64,
                "cutout_b64": _png_b64(cutout, f"cutout {index}"),
            }
        )

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "Auto mask pick debug complete: candidates=%d winner=%s elapsed_ms=%.1f",
        len(candidates),
        selection.winner_index,
        elapsed_ms,
    )
    return {
        "click_xy": [x, y],
        "threshold": float(DEFAULT_THRESHOLD),
        "winner_index": selection.winner_index,
        "candidates": candidates,
        "elapsed_ms": elapsed_ms,
    }


def run_inpaint_verify(
    image_bytes: bytes,
    *,
    x: int,
    y: int,
    mask_index: int | None,
) -> dict[str, Any]:
    """Inpaint one click-candidate and return the CLIP verify retry trace."""
    start = time.monotonic()
    bgr = _decode_bgr(image_bytes, label="inpaint-verify")
    _validate_click(bgr, x, y)

    select_best_cutout = load_avroom_attr("select_best_cutout")

    pairs = _segment_click(image_bytes, bgr, x, y)
    if not pairs:
        raise ValueError("Segmentation returned no candidates.")

    cutouts = [cutout for _mask, cutout in pairs]
    selection = select_best_cutout(
        cutouts,
        click_xy=(x, y),
        scorer=_get_cutout_clip_scorer(),
    )
    chosen = mask_index if mask_index is not None else selection.winner_index
    if chosen is None:
        raise ValueError("no viable mask")
    if chosen < 0 or chosen >= len(pairs):
        raise ValueError(f"mask_index {chosen} is out of range (0..{len(pairs) - 1}).")

    refined_mask, cutout = pairs[chosen]
    if cutout.ndim == 3 and cutout.shape[2] >= 4:
        compose_mask = cutout[:, :, 3]
    else:
        compose_mask = refined_mask

    verify_trace: list[dict[str, Any]] = []
    inpaint_out: dict[str, Any] = {}
    BackgroundInpainter = load_avroom_attr("BackgroundInpainter")
    inpainter = BackgroundInpainter()
    final_bgr = inpainter.cut_mask_from_image(
        bgr,
        refined_mask,
        compose_mask=compose_mask,
        inpaint_out=inpaint_out,
        verify_trace=verify_trace,
    )

    attempts: list[dict[str, Any]] = []
    lama_b64: str | None = None
    for entry in verify_trace:
        if entry.get("lama_bgr") is not None and lama_b64 is None:
            lama_b64 = _png_b64(entry["lama_bgr"], "lama")
        params = entry["params"]
        attempts.append(
            {
                "attempt_index": entry["attempt_index"],
                "ok": entry["ok"],
                "sd_skipped": entry["sd_skipped"],
                "scores": entry["scores"],
                "winner_label": entry["winner_label"],
                "params": params,
                "param_fixes_json": entry["param_fixes_json"],
                "mask_dilate_pixels": entry.get("mask_dilate_pixels", 0),
                "compose_dilate_pixels": entry.get("compose_dilate_pixels", 0),
                "mask_pixel_count": entry.get("mask_pixel_count", 0),
                "next_params": entry.get("next_params"),
                "candidate_b64": _png_b64(entry["candidate_bgr"], f"candidate {entry['attempt_index']}"),
                "clip_crop_b64": _png_b64(entry["clip_crop_bgr"], f"clip crop {entry['attempt_index']}"),
            }
        )
        original_crop = entry.get("verify_original_crop_bgr")
        if original_crop is not None:
            attempts[-1]["verify_original_crop_b64"] = _png_b64(
                original_crop,
                f"original crop {entry['attempt_index']}",
            )

    passed = bool(attempts) and bool(attempts[-1]["ok"])
    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "Inpaint verify debug complete: mask_index=%d attempts=%d passed=%s elapsed_ms=%.1f",
        chosen,
        len(attempts),
        passed,
        elapsed_ms,
    )
    return {
        "click_xy": [x, y],
        "mask_index": chosen,
        "passed": passed,
        "retries_exhausted": not passed,
        "lama_b64": lama_b64,
        "final_b64": _png_b64(final_bgr, "final inpaint"),
        "attempts": attempts,
        "elapsed_ms": elapsed_ms,
    }
