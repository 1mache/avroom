from __future__ import annotations

from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


def to_pil_rgba(image: bytes | np.ndarray | Image.Image | Path | str) -> Image.Image:
    """Convert any supported image representation to a PIL RGBA image.

    Accepted inputs:
    - ``bytes``: raw PNG/JPEG file bytes (e.g. directly from FastAPI's /images/click).
    - ``numpy.ndarray``: assumed BGRA (H,W,4) when 4-channel — the format
      ObjectRemover produces — or BGR (H,W,3). Converted via OpenCV.
    - ``PIL.Image``: converted to RGBA if not already.
    - ``pathlib.Path`` or ``str``: loaded from disk.

    Raises ``TypeError`` for unsupported types.
    Raises ``ValueError`` if bytes/path cannot be decoded as an image.
    """

    if isinstance(image, bytes):
        try:
            return Image.open(BytesIO(image)).convert("RGBA")
        except UnidentifiedImageError as exc:
            raise ValueError("Bytes do not represent a valid image.") from exc

    if isinstance(image, np.ndarray):
        return _ndarray_to_pil_rgba(image)

    if isinstance(image, Image.Image):
        return image.convert("RGBA")

    if isinstance(image, (Path, str)):
        try:
            return Image.open(image).convert("RGBA")
        except (FileNotFoundError, UnidentifiedImageError) as exc:
            raise ValueError(f"Cannot open image from path: {image}") from exc

    raise TypeError(
        f"Unsupported image type {type(image).__name__!r}. "
        "Expected bytes, numpy.ndarray, PIL.Image, pathlib.Path, or str."
    )


def _ndarray_to_pil_rgba(arr: np.ndarray) -> Image.Image:
    """Convert a numpy array (BGR or BGRA, uint8) to PIL RGBA."""

    if arr.ndim != 3:
        raise ValueError(f"Expected 3-D array (H,W,C), got shape {arr.shape}.")

    channels = arr.shape[2]
    if channels == 4:
        # BGRA (ObjectRemover convention) → RGBA
        rgba = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGBA)
    elif channels == 3:
        # BGR → RGBA (fully opaque)
        rgba = cv2.cvtColor(arr, cv2.COLOR_BGR2RGBA)
    else:
        raise ValueError(
            f"Array has {channels} channels; expected 3 (BGR) or 4 (BGRA)."
        )

    return Image.fromarray(rgba, mode="RGBA")
