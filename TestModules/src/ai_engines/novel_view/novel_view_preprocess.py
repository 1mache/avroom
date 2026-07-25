from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_MODEL_SIZE = 256
DEFAULT_BG_THRESHOLD = 245


@dataclass(frozen=True)
class PreprocessResult:
    """Square model input plus metadata to map the output back to canvas space."""

    model_image: Image.Image
    crop_box: tuple[int, int, int, int]
    square_size: int
    canvas_size: tuple[int, int]


def crop_alpha_bbox(rgba: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Crop ``rgba`` to the tight alpha bounding box.

    Returns:
        Tuple of (cropped image, ``(left, top, right, bottom)`` in original coords).
    """

    arr = np.array(rgba.convert("RGBA"))
    alpha = arr[:, :, 3]
    points = cv2.findNonZero(alpha)
    if points is None:
        height, width = alpha.shape
        logger.warning("Empty alpha channel; using full image bounds")
        return rgba.convert("RGBA"), (0, 0, width, height)

    x, y, w, h = cv2.boundingRect(points)
    left, top, right, bottom = x, y, x + w, y + h
    cropped = rgba.crop((left, top, right, bottom))
    return cropped.convert("RGBA"), (left, top, right, bottom)


def pad_to_square(image: Image.Image, fill: tuple[int, int, int, int] = (255, 255, 255, 0)) -> Image.Image:
    """Center ``image`` on a square canvas with transparent padding."""

    width, height = image.size
    side = max(width, height)
    canvas = Image.new("RGBA", (side, side), fill)
    offset_x = (side - width) // 2
    offset_y = (side - height) // 2
    canvas.paste(image, (offset_x, offset_y), image)
    return canvas


def prepare_cutout_for_model(
    rgba: Image.Image,
    *,
    model_size: int = DEFAULT_MODEL_SIZE,
) -> PreprocessResult:
    """Crop, square-pad, and resize a cutout for Zero123-class model input."""

    canvas_w, canvas_h = rgba.size
    cropped, crop_box = crop_alpha_bbox(rgba)
    square = pad_to_square(cropped)
    square_size = square.size[0]
    model_image = square.resize((model_size, model_size), Image.Resampling.LANCZOS)
    logger.debug(
        "Prepared cutout for model: canvas=%sx%s crop=%s square=%d model=%d",
        canvas_w,
        canvas_h,
        crop_box,
        square_size,
        model_size,
    )
    return PreprocessResult(
        model_image=model_image,
        crop_box=crop_box,
        square_size=square_size,
        canvas_size=(canvas_w, canvas_h),
    )


def rgb_to_rgba_with_white_background(
    rgb: Image.Image,
    *,
    threshold: int = DEFAULT_BG_THRESHOLD,
) -> Image.Image:
    """Convert an RGB model output to RGBA by making near-white pixels transparent."""

    rgba = rgb.convert("RGBA")
    arr = np.array(rgba)
    rgb_channels = arr[:, :, :3]
    white_mask = np.all(rgb_channels >= threshold, axis=2)
    arr[white_mask, 3] = 0
    return Image.fromarray(arr, mode="RGBA")


def composite_model_output_on_canvas(
    model_rgba: Image.Image,
    prep: PreprocessResult,
) -> np.ndarray:
    """Upscale model output and place it back on a full-size transparent canvas."""

    square = model_rgba.resize(
        (prep.square_size, prep.square_size),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", prep.canvas_size, (0, 0, 0, 0))
    left, top, _, _ = prep.crop_box
    paste_x = left - (prep.square_size - (prep.crop_box[2] - prep.crop_box[0])) // 2
    paste_y = top - (prep.square_size - (prep.crop_box[3] - prep.crop_box[1])) // 2
    canvas.paste(square, (paste_x, paste_y), square)

    arr = np.array(canvas)
    rgba = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)
    return rgba.astype(np.uint8)
