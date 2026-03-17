from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageDraw, UnidentifiedImageError

from schemas.image import ImageProcessingOptions


logger = logging.getLogger(__name__)


def get_image_path(image_id: str, base_dir: Path) -> Path:
    """Resolve filesystem path for a stored image regardless of extension."""

    candidates = sorted(base_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise FileNotFoundError(f"No stored image found for image_id='{image_id}' in {base_dir}")
    return candidates[0]


def load_image_bytes(image_id: str, base_dir: Path) -> bytes:
    """Load raw image bytes for a given `image_id` from disk.

    The caller is responsible for handling any filesystem-related exceptions
    that may occur if the image does not exist.
    """

    image_path = get_image_path(image_id=image_id, base_dir=base_dir)
    return image_path.read_bytes()


def segment_at_click(
    image_bytes: bytes,
    x: int,
    y: int,
    options: ImageProcessingOptions | None = None,
) -> tuple[bytes, bytes, str]:
    """Segmentation stub that returns background and cutout images.

    - `image_bytes` are the bytes of the original image.
    - `x`, `y` are the click coordinates in pixels (origin top-left).
    - `options` can be used to configure the segmentation behavior.

    This function is where the real segmentation logic will ultimately live.
    For now, it simply returns the original bytes for both background and cutout
    so the API and frontend integration can be wired up independently.
    """

    if not image_bytes:
        return b"", b"", "png"

    # === CLICK-BASED SEGMENTATION LOGIC GOES HERE ===

    _ = (x, y, options) # delete this after pasting
    background_bytes = image_bytes
    cutout_bytes = image_bytes
    image_format = "png"
    return background_bytes, cutout_bytes, image_format


def process_click_on_image(
    image_id: str,
    base_dir: Path,
    x: int,
    y: int,
    options: ImageProcessingOptions | None = None,
) -> tuple[bytes, bytes, str]:
    """High-level click-based processing function wired to disk storage.

    This helper ties together the idea of an `image_id` (used by the API) and
    the pure segmentation logic defined in `segment_at_click`.
    """

    image_path = get_image_path(image_id=image_id, base_dir=base_dir)
    image_bytes = load_image_bytes(image_id=image_id, base_dir=base_dir)

    try:
        with Image.open(io.BytesIO(image_bytes)) as source_image:
            width, height = source_image.size
            in_bounds = 0 <= x < width and 0 <= y < height

            if not in_bounds:
                logger.warning(
                    "Click out of bounds for image_id='%s': x=%d y=%d image_width=%d image_height=%d",
                    image_id,
                    x,
                    y,
                    width,
                    height,
                )

            debug_image = source_image.convert("RGB")
            if in_bounds:
                draw = ImageDraw.Draw(debug_image)
                radius = 6
                draw.ellipse(
                    (x - radius, y - radius, x + radius, y + radius),
                    fill="red",
                    outline="white",
                    width=2,
                )

            tmp_dir = base_dir / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            debug_image_path = tmp_dir / f"{image_id}_debug{image_path.suffix}"
            debug_image.save(debug_image_path)
    except UnidentifiedImageError:
        logger.exception("Unable to open image bytes for image_id='%s'", image_id)

    background_bytes, cutout_bytes, image_format = segment_at_click(
        image_bytes=image_bytes,
        x=x,
        y=y,
        options=options,
    )
    return background_bytes, cutout_bytes, image_format

