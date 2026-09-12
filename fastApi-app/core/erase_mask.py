"""Decoding and splitting the freehand erase mask the lasso tool sends.

Pure array work: base64 PNG in, boolean mask out, then that mask split into
its disconnected blobs so one lasso gesture covering two separate regions
becomes two removals instead of one mask with a hole between them. No disk,
no models, no session -- which is why it sits apart from the erase *pipeline*
in `core/image_processing.py` that consumes it.
"""

from __future__ import annotations

import base64
import io
import logging

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


ERASE_MIN_COMPONENT_PIXELS = 64


def canvas_shape_from_bytes(image_bytes: bytes) -> tuple[int, int]:
    """Return (height, width) for stored canvas/upload bytes."""

    with Image.open(io.BytesIO(image_bytes)) as source_image:
        width, height = source_image.size
    return height, width


def decode_erase_mask_png(mask_b64: str, expected_shape: tuple[int, int]) -> np.ndarray:
    """Decode a client-drawn erase mask PNG into uint8 HxW with values 0/255.

    Args:
        mask_b64: Base64-encoded PNG (grayscale or RGB — luminance is used).
        expected_shape: ``(height, width)`` of the session canvas.

    Raises:
        ValueError: When decoding fails, shapes mismatch, or the mask is empty.
    """

    try:
        raw = base64.b64decode(mask_b64, validate=True)
    except Exception as exc:
        raise ValueError("Erase mask is not valid base64.") from exc

    try:
        with Image.open(io.BytesIO(raw)) as img:
            gray = img.convert("L")
            if gray.size != (expected_shape[1], expected_shape[0]):
                raise ValueError(
                    f"Erase mask shape {gray.size[::-1]} does not match canvas {expected_shape}."
                )
            arr = np.array(gray, dtype=np.uint8)
    except UnidentifiedImageError as exc:
        raise ValueError("Erase mask is not a valid PNG image.") from exc

    mask = np.where(arr >= 128, 255, 0).astype(np.uint8)
    if not np.any(mask):
        raise ValueError("Erase mask has no foreground pixels.")
    return mask


def split_mask_components(
    mask: np.ndarray,
    min_pixels: int = ERASE_MIN_COMPONENT_PIXELS,
) -> list[np.ndarray]:
    """Split a binary mask into disconnected 8-connected foreground blobs.

    Drops blobs smaller than ``min_pixels`` (lasso speckle). Raises when
    nothing usable remains.
    """

    _, labels = cv2.connectedComponents((mask > 0).astype(np.uint8), connectivity=8)
    components: list[np.ndarray] = []
    for label in range(1, int(labels.max()) + 1):
        component = np.where(labels == label, 255, 0).astype(np.uint8)
        if int(np.count_nonzero(component)) >= min_pixels:
            components.append(component)
    if not components:
        raise ValueError("Erase mask has no foreground blobs large enough to erase.")
    return components


