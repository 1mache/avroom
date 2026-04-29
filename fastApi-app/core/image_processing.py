from __future__ import annotations

import hashlib
import io
import logging

import cv2

from pathlib import Path

from PIL import Image, ImageDraw, UnidentifiedImageError

from schemas.image import ImageProcessingOptions


logger = logging.getLogger(__name__)


def _get_object_remover_class():
    try:
        from avroom_object_removal.core.objectRemover import ObjectRemover
    except ModuleNotFoundError as exc:
        if exc.name == "avroom_object_removal":
            raise RuntimeError(
                "Missing local package `avroom_object_removal`. Install repo dependencies or run `pip install -e ./TestModules`."
            ) from exc
        raise

    return ObjectRemover


def _create_debug_click_image(source_image: Image.Image, x: int, y: int, base_dir: Path, image_id: str):
    """Create RGB debug image with a marker drawn at click coordinates."""

    RADIUS = 6
    DEBUG_DIR_SUBPATH = "tmp"

    debug_image: Image.Image = source_image.convert("RGB")
    draw = ImageDraw.Draw(debug_image)
    draw.ellipse(
        (x - RADIUS, y - RADIUS, x + RADIUS, y + RADIUS),
        fill="red",
        outline="white",
        width=2,
    )

    tmp_dir = base_dir / DEBUG_DIR_SUBPATH
    tmp_dir.mkdir(parents=True, exist_ok=True)
    debug_image_path = tmp_dir / f"{image_id}_debug.png"
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
    """

    if not image_bytes:
        return b"", b"", "png"

    remover = _get_object_remover_class()()
    image_key = f"memory://{hashlib.sha256(image_bytes).hexdigest()}"
    background_bgr, cutout_bgra = remover.remove_object(
        image_path=image_key,
        x=x,
        y=y,
        image_bytes=image_bytes,
    )

    ok_bg, bg_buf = cv2.imencode(".png", background_bgr)
    ok_co, co_buf = cv2.imencode(".png", cutout_bgra)
    if not ok_bg or bg_buf is None:
        raise RuntimeError("Failed to encode background image to PNG.")
    if not ok_co or co_buf is None:
        raise RuntimeError("Failed to encode cutout image to PNG.")

    background_bytes = bg_buf.tobytes()
    cutout_bytes = co_buf.tobytes()
    return background_bytes, cutout_bytes, "png"


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

    image_bytes = load_image_bytes(image_id=image_id, base_dir=base_dir)

    try:
        with Image.open(io.BytesIO(image_bytes)) as source_image:
            width, height = source_image.size

            # bounds check
            if not (0 <= x < width and 0 <= y < height):
                logger.error(
                    "Click out of bounds for image_id='%s': x=%d y=%d image_width=%d image_height=%d",
                    image_id,
                    x,
                    y,
                    width,
                    height,
                )
                raise ValueError(f"Click coordinates (x={x}, y={y}) are out of bounds for image size {width}x{height}.")

            _create_debug_click_image(source_image, x, y, base_dir, image_id)

    except UnidentifiedImageError as exc:
        logger.exception("Unable to open image bytes for image_id='%s'", image_id)
        raise ValueError(f"Stored file for image_id='{image_id}' is not a valid image.") from exc

    background_bytes, cutout_bytes, image_format = segment_at_click(
        image_bytes=image_bytes,
        x=x,
        y=y,
        options=options,
    )
    return background_bytes, cutout_bytes, image_format

