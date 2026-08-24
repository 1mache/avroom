from __future__ import annotations

import logging

import cv2
import numpy as np

from ..ai_engines.depth.depth_mapping_facade import DepthMappingFacade

logger = logging.getLogger(__name__)


def load_image(image_path: str, image_bytes: bytes | None, *, log_context: str) -> np.ndarray:
    """Decode ``image_bytes`` in memory if given, else read ``image_path`` from disk.

    Shared by :class:`ObjectRemover` and :class:`ObjectSegmentor`, whose first
    pipeline stage is identical. ``log_context`` names the caller in the
    decode-failure log line (e.g. ``"inpaint pipeline"``).
    """
    if image_bytes is not None:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            logger.error(f"Could not decode image bytes for {log_context}")
            raise ValueError("Could not decode image bytes into an image array")
        return image

    image = cv2.imread(image_path)
    if image is None:
        logger.error(f"Could not load image: {image_path}")
        raise FileNotFoundError(f"Could not load image: {image_path}")
    return image


def compute_depth(
    image: np.ndarray,
    depth_map: np.ndarray | None,
    depth_facade: DepthMappingFacade,
) -> np.ndarray:
    """Return ``depth_map`` unchanged if supplied, else compute it via ``depth_facade``.

    Shared by :class:`ObjectRemover` and :class:`ObjectSegmentor` — both accept
    an optional precomputed depth map (caller-side session cache) and fall
    back to the same facade call otherwise.
    """
    if depth_map is not None:
        logger.info("Step 1: Using precomputed depth map...")
        return depth_map
    logger.info("Step 1: Computing optimized depth map...")
    return depth_facade.map_depth(image)
