from __future__ import annotations

"""Shared encoding helpers for image payloads crossing the API boundary.

Both the pipeline layer and the HTTP layer need the same two conversions --
OpenCV array to PNG bytes, and bytes to the base64 string the frontend renders
as a data URL -- so they live here instead of being re-implemented per module.
"""

import base64
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def encode_png(image: np.ndarray, label: str) -> bytes:
    """Encode an OpenCV image array as PNG bytes.

    Args:
        image: BGR or BGRA uint8 array.
        label: Human-readable name of the image, used in the failure message.

    Raises:
        RuntimeError: When OpenCV cannot encode the array.
    """

    ok, buffer = cv2.imencode(".png", image)
    if not ok or buffer is None:
        logger.error("Failed to encode %s image to PNG", label)
        raise RuntimeError(f"Failed to encode {label} image to PNG.")
    return buffer.tobytes()


def to_base64_ascii(data: bytes) -> str:
    """Return the base64 ASCII string for raw bytes, ready for a JSON response."""

    return base64.b64encode(data).decode("ascii")
