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
from core.image_codec import encode_png

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
