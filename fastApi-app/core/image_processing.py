from __future__ import annotations

import hashlib
import io
import logging

import cv2
import numpy as np

from pathlib import Path

from PIL import Image, ImageDraw, UnidentifiedImageError

from schemas.image import ImageProcessingOptions
from core.mask_cache import delete_candidates, load_cutout_bytes, load_refined_mask, mask_id_from_index, save_candidate
from core.object_storage import current_background_path


logger = logging.getLogger(__name__)


def _get_object_remover_class():
    try:
        from avroom_object_removal import ObjectRemover
    except ModuleNotFoundError as exc:
        if exc.name == "avroom_object_removal":
            logger.error("avroom_object_removal package not importable")
            raise RuntimeError(
                "Missing local package `avroom_object_removal`. Install repo dependencies or run `pip install -e ./TestModules`."
            ) from exc
        raise

    return ObjectRemover


def _get_object_segmentor_class():
    try:
        from avroom_object_removal import ObjectSegmentor
    except ModuleNotFoundError as exc:
        if exc.name == "avroom_object_removal":
            logger.error("avroom_object_removal package not importable")
            raise RuntimeError(
                "Missing local package `avroom_object_removal`. Install repo dependencies or run `pip install -e ./TestModules`."
            ) from exc
        raise

    return ObjectSegmentor


def _get_background_inpainter_class():
    try:
        from avroom_object_removal import BackgroundInpainter
    except ModuleNotFoundError as exc:
        if exc.name == "avroom_object_removal":
            logger.error("avroom_object_removal package not importable")
            raise RuntimeError(
                "Missing local package `avroom_object_removal`. Install repo dependencies or run `pip install -e ./TestModules`."
            ) from exc
        raise

    return BackgroundInpainter


def _create_debug_click_image(source_image: Image.Image, x: int, y: int, base_dir: Path, image_id: str):
    """Create RGB debug image with a marker drawn at click coordinates."""

    RADIUS = 6
    DEBUG_DIR_SUBPATH = "point"

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
        logger.info(
            "Loaded canvas bytes: image_id=%s source=background bytes=%d",
            image_id,
            len(canvas_bytes),
        )
        return canvas_bytes

    original_bytes = load_image_bytes(image_id=image_id, base_dir=base_dir)
    logger.info(
        "Loaded canvas bytes: image_id=%s source=original bytes=%d",
        image_id,
        len(original_bytes),
    )
    return original_bytes


def _validate_click_coordinates(image_bytes: bytes, x: int, y: int, base_dir: Path, image_id: str) -> None:
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
                raise ValueError(f"Click coordinates (x={x}, y={y}) are out of bounds for image size {width}x{height}.")
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


def _decode_original_bgr(image_bytes: bytes, image_id: str) -> np.ndarray:
    """Decode stored image bytes into OpenCV BGR array for inpainting."""

    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        logger.error("Could not decode original image bytes: image_id=%s", image_id)
        raise ValueError(f"Stored file for image_id='{image_id}' is not a valid image.")
    return decoded


def _encode_png(image: np.ndarray, label: str) -> bytes:
    """Encode OpenCV image array as PNG bytes."""

    ok, buffer = cv2.imencode(".png", image)
    if not ok or buffer is None:
        logger.error("Failed to encode %s image to PNG", label)
        raise RuntimeError(f"Failed to encode {label} image to PNG.")
    return buffer.tobytes()


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
        logger.warning("segment_at_click called with empty bytes — returning empty result")
        return b"", b"", "png"

    remover = _get_object_remover_class()()
    image_key = f"memory://{hashlib.sha256(image_bytes).hexdigest()}"

    logger.info("Running ObjectRemover: image_key=%s click=(%d,%d)", image_key, x, y)
    background_bgr, cutout_bgra = remover.remove_object(
        image_path=image_key,
        x=x,
        y=y,
        image_bytes=image_bytes,
    )
    logger.info(
        "ObjectRemover finished: bg_shape=%s cutout_shape=%s",
        background_bgr.shape,
        cutout_bgra.shape,
    )

    ok_bg, bg_buf = cv2.imencode(".png", background_bgr)
    ok_co, co_buf = cv2.imencode(".png", cutout_bgra)
    if not ok_bg or bg_buf is None:
        logger.error("Failed to encode background image to PNG")
        raise RuntimeError("Failed to encode background image to PNG.")
    if not ok_co or co_buf is None:
        logger.error("Failed to encode cutout image to PNG")
        raise RuntimeError("Failed to encode cutout image to PNG.")

    background_bytes = bg_buf.tobytes()
    cutout_bytes = co_buf.tobytes()
    logger.debug(
        "Encoded result: bg_bytes=%d cutout_bytes=%d",
        len(background_bytes),
        len(cutout_bytes),
    )
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
    logger.debug("Loaded image bytes: image_id=%s bytes=%d", image_id, len(image_bytes))

    _validate_click_coordinates(image_bytes, x, y, base_dir, image_id)

    background_bytes, cutout_bytes, image_format = segment_at_click(
        image_bytes=image_bytes,
        x=x,
        y=y,
        options=options,
    )

    return background_bytes, cutout_bytes, image_format


def segment_candidates_on_image(
    image_id: str,
    base_dir: Path,
    x: int,
    y: int,
    options: ImageProcessingOptions | None = None,
) -> list[tuple[str, bytes]]:
    """Run segmentation only and cache every candidate mask.

    The returned bytes are BGRA cutout previews for the frontend. The matching
    refined masks stay on disk as `.npy` files because JSON/base64 is wasteful
    and inpainting needs exact pixel arrays, not visualized masks.
    """

    del options  # TODO: parameter not used. legacy click options. remove it or use
    image_bytes = load_canvas_bytes(image_id=image_id, base_dir=base_dir)
    logger.debug("Loaded canvas bytes for segmentation: image_id=%s bytes=%d", image_id, len(image_bytes))
    _validate_click_coordinates(image_bytes, x, y, base_dir, image_id)

    # New segmentation invalidates any older unchosen candidates for this image.
    delete_candidates(base_dir, image_id)

    segmentor = _get_object_segmentor_class()()
    # Hash image bytes → build cache key. memory:// prefix tells the AI pipeline
    # "don't read disk, use this hash to find cached model state."
    image_key = f"memory://{hashlib.sha256(image_bytes).hexdigest()}"
    logger.info("Running ObjectSegmentor: image_key=%s click=(%d,%d)", image_key, x, y)
    candidate_pairs = segmentor.get_mask_for_object_at_position(
        image_path=image_key,
        x=x,
        y=y,
        image_bytes=image_bytes,
    )
    logger.info("ObjectSegmentor finished: image_id=%s candidates=%d", image_id, len(candidate_pairs))

    results: list[tuple[str, bytes]] = []
    for index, (refined_mask, cutout_bgra) in enumerate(candidate_pairs):
        mask_id = mask_id_from_index(index)
        cutout_bytes = _encode_png(cutout_bgra, f"candidate cutout {mask_id}")
        save_candidate(base_dir, image_id, mask_id, refined_mask, cutout_bytes)
        results.append((mask_id, cutout_bytes))

    return results


def inpaint_selected_mask_on_image(
    image_id: str,
    mask_id: str,
    base_dir: Path,
) -> tuple[bytes, bytes, str]:
    """Run background inpainting for one previously cached mask candidate."""

    image_bytes = load_canvas_bytes(image_id=image_id, base_dir=base_dir)
    source_bgr = _decode_original_bgr(image_bytes, image_id)
    refined_mask = load_refined_mask(base_dir, image_id, mask_id)
    cutout_bytes = load_cutout_bytes(base_dir, image_id, mask_id)

    inpainter = _get_background_inpainter_class()()
    logger.info(
        "Running BackgroundInpainter: image_id=%s mask_id=%s image_shape=%s mask_shape=%s",
        image_id,
        mask_id,
        source_bgr.shape,
        refined_mask.shape,
    )
    background_bgr = inpainter.cut_mask_from_image(original_image=source_bgr, mask=refined_mask)
    logger.info("BackgroundInpainter finished: image_id=%s mask_id=%s bg_shape=%s", image_id, mask_id, background_bgr.shape)

    background_bytes = _encode_png(background_bgr, "background")
    return background_bytes, cutout_bytes, "png"

