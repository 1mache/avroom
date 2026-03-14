from __future__ import annotations

from pathlib import Path

from schemas.image import ImageProcessingOptions


def process_image(input_bytes: bytes, options: ImageProcessingOptions) -> bytes:
    """Process an uploaded image and return the output image bytes.

    - `input_bytes` are the raw bytes of the uploaded file.
    - `options` describes user-requested processing parameters (format, flags).

    This function is intentionally a stub for the MVP. Replace the marked region
    with your real image processing pipeline later.
    """

    if not input_bytes:
        # Defensive check: an empty upload can't be processed meaningfully.
        return b""

    # === IMAGE PROCESSING LOGIC GOES HERE ===
    # Typical pipeline (example):
    # 1) Decode bytes -> image object (e.g. Pillow / OpenCV / etc.)
    # 2) Apply transforms (resize, grayscale, detect objects, ...)
    # 3) Encode image object -> bytes in the requested output format
    #
    # For MVP outline purposes we return the original bytes unchanged.
    _ = options  # Options are currently unused by the stub implementation.
    return input_bytes


def get_image_path(image_id: str, base_dir: Path) -> Path:
    """Build the filesystem path for a stored image.

    The concrete file extension can be adjusted later. For the outline we assume
    PNG output, which is a common choice for segmentation results.
    """

    return base_dir / f"{image_id}.png"


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
    # Conceptual pipeline:
    # 1) Decode bytes -> image object.
    # 2) Use `x`, `y` (and optionally `options`) to locate the clicked object.
    # 3) Produce two images:
    #    - Background with the clicked object removed.
    #    - Cutout image containing only the clicked object.
    # 4) Encode both images back to bytes in the desired format.
    _ = (x, y, options)
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

    image_bytes = load_image_bytes(image_id=image_id, base_dir=base_dir)
    background_bytes, cutout_bytes, image_format = segment_at_click(
        image_bytes=image_bytes,
        x=x,
        y=y,
        options=options,
    )
    return background_bytes, cutout_bytes, image_format

