"""Reading a session's images off disk, and decoding them.

The leaf layer under `core/image_processing.py`: resolving where a session's
original upload and cumulative background canvas live, loading their bytes,
and turning those bytes into the arrays the pipeline works on. Nothing here
knows about segmentation, inpainting or placement -- it is the same handful of
file/decode primitives every one of those stages starts from.

The debug click overlay lives here too, since it is written straight to disk
beside the images and is the only other thing in this module that touches the
storage dir directly.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, UnidentifiedImageError

from core.object_storage import current_background_path

logger = logging.getLogger(__name__)

# Debug click overlays live in their own subdirectory so they are never picked
# up by the session artifact globs that scan the storage dir itself.
DEBUG_DIR_SUBPATH = "point"
_DEBUG_MARKER_RADIUS_PX = 6
_DEBUG_MARKER_OUTLINE_PX = 2


def debug_click_image_path(base_dir: Path, image_id: str) -> Path:
    """Return the canonical path of a session's debug click overlay."""

    return base_dir / DEBUG_DIR_SUBPATH / f"{image_id}_debug.png"


def _create_debug_click_image(
    source_image: Image.Image,
    x: int,
    y: int,
    base_dir: Path,
    image_id: str,
) -> None:
    """Create RGB debug image with a marker drawn at click coordinates."""

    debug_image: Image.Image = source_image.convert("RGB")
    draw = ImageDraw.Draw(debug_image)
    draw.ellipse(
        (
            x - _DEBUG_MARKER_RADIUS_PX,
            y - _DEBUG_MARKER_RADIUS_PX,
            x + _DEBUG_MARKER_RADIUS_PX,
            y + _DEBUG_MARKER_RADIUS_PX,
        ),
        fill="red",
        outline="white",
        width=_DEBUG_MARKER_OUTLINE_PX,
    )

    debug_image_path = debug_click_image_path(base_dir, image_id)
    debug_image_path.parent.mkdir(parents=True, exist_ok=True)
    debug_image.save(debug_image_path)


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


def load_canvas_bytes(image_id: str, base_dir: Path) -> bytes:
    """Load the cumulative background canvas bytes for progressive removal.

    For progressive removal, each subsequent segmentation/inpainting operation
    should work on the latest state of the room — i.e., the canvas that already
    has previously removed objects replaced by inpainted background. If such a
    canvas exists (``{image_id}_background.png``), it is returned; otherwise the
    original upload is used as the starting point.

    Args:
        image_id: Session image identifier.
        base_dir: Directory that contains session artifacts.

    Returns:
        Raw PNG/image bytes of the canvas (background if available, original otherwise).
    """

    canvas_path = current_background_path(base_dir, image_id)
    if canvas_path.exists():
        canvas_bytes = canvas_path.read_bytes()
        logger.debug(
            "Loaded canvas bytes: image_id=%s source=background bytes=%d",
            image_id,
            len(canvas_bytes),
        )
        return canvas_bytes

    original_bytes = load_image_bytes(image_id=image_id, base_dir=base_dir)
    logger.debug(
        "Loaded canvas bytes: image_id=%s source=original bytes=%d",
        image_id,
        len(original_bytes),
    )
    return original_bytes


def validate_click_coordinates(
    image_bytes: bytes, x: int, y: int, base_dir: Path, image_id: str
) -> None:
    """Validate natural-image click coordinates and write debug click overlay."""

    try:
        with Image.open(io.BytesIO(image_bytes)) as source_image:
            width, height = source_image.size

            if not (0 <= x < width and 0 <= y < height):
                logger.error(
                    "Click out of bounds for image_id='%s': x=%d y=%d image_width=%d image_height=%d",
                    image_id,
                    x,
                    y,
                    width,
                    height,
                )
                raise ValueError(
                    f"Click coordinates (x={x}, y={y}) are out of bounds for image size {width}x{height}."
                )
            logger.debug(
                "Click within bounds: image_id=%s click=(%d,%d) size=%dx%d",
                image_id,
                x,
                y,
                width,
                height,
            )

            _create_debug_click_image(source_image, x, y, base_dir, image_id)
            logger.debug("Saved debug click overlay: image_id=%s", image_id)

    except UnidentifiedImageError as exc:
        logger.exception("Unable to open image bytes for image_id='%s'", image_id)
        raise ValueError(f"Stored file for image_id='{image_id}' is not a valid image.") from exc


def decode_original_bgr(image_bytes: bytes, image_id: str) -> np.ndarray:
    """Decode stored image bytes into OpenCV BGR array for inpainting."""

    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        logger.error("Could not decode original image bytes: image_id=%s", image_id)
        raise ValueError(f"Stored file for image_id='{image_id}' is not a valid image.")
    return decoded


def decode_cutout_alpha(cutout_bytes: bytes, image_id: str, mask_id: str) -> np.ndarray:
    """Decode cached cutout PNG alpha channel as a compose mask."""

    decoded = cv2.imdecode(np.frombuffer(cutout_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None or decoded.ndim < 3 or decoded.shape[2] < 4:
        logger.error(
            "Could not decode cutout alpha: image_id=%s mask_id=%s shape=%s",
            image_id,
            mask_id,
            None if decoded is None else decoded.shape,
        )
        raise ValueError(
            f"Cached cutout for image_id='{image_id}', mask_id='{mask_id}' is not a valid BGRA PNG."
        )
    return decoded[:, :, 3]


