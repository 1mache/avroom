from __future__ import annotations

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


def process_click_on_image(
    image_id: str,
    x: int,
    y: int,
    options: ImageProcessingOptions | None = None,
) -> bytes | None:
    """Click-based processing stub.

    - `image_id` identifies which previously uploaded image the click refers to.
      For now there is no persistence, so this is a placeholder for future storage.
    - `x`, `y` are pixel coordinates (origin top-left).
    - `options` are optional processing parameters.

    For the MVP, this is a hook point only. Once you store images, this function
    will load the image by `image_id`, apply click-conditioned processing, and
    return output bytes.
    """

    # === CLICK-BASED IMAGE PROCESSING LOGIC GOES HERE ===
    _ = (image_id, x, y, options)
    return None

