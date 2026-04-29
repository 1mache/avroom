from __future__ import annotations

import functools
import logging
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ..image_inpainting_strategy import ImageInpaintingStrategy

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _load_simple_lama() -> Any:
    """Load and cache a single ``SimpleLama`` instance per process.

    Replaces the legacy class-level Singleton in ``LamaInpainter``.
    """
    from simple_lama_inpainting import SimpleLama

    logger.info("Loading LaMa model into memory...")
    return SimpleLama()


class LamaInpaintingStrategy(ImageInpaintingStrategy):
    """LaMa-based structural inpainting strategy.

    LaMa is excellent at filling masked regions with plausible structure
    (walls, floors, repeating textures) but tends to produce subtle
    discoloration around the boundary. The pipeline pairs it with Stable
    Diffusion (via :class:`HybridInpaintingStrategy`) when a higher-fidelity
    finish is desired.
    """

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
        logger.info("Starting LaMa inpainting process...")

        if mask.ndim == 3:
            mask = mask[:, :, 0]
        if mask.shape[:2] != image.shape[:2]:
            mask = cv2.resize(
                mask,
                (image.shape[1], image.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
            thresh = 0.5 if mask.max() <= 1.0 else 127
            mask = (mask > thresh).astype(np.uint8) * 255

        # Pre-fill mask interior with the mean color of the immediate boundary
        # ring. Without this, LaMa is conditioned on the to-be-removed object
        # and tends to leave a faint ghost where it occluded another object.
        mask_uint = (mask * 255).astype(np.uint8) if mask.max() <= 1 else mask.astype(np.uint8)
        mask_bool = mask_uint > 127
        if mask_bool.any():
            kernel = np.ones((3, 3), np.uint8)
            boundary = (cv2.dilate(mask_uint, kernel) > 0) & (~mask_bool)
            if boundary.any():
                if len(image.shape) == 3:
                    fill = np.round(image[boundary].mean(axis=0)).astype(image.dtype)
                else:
                    fill = np.round(image[boundary].mean()).astype(image.dtype)
                image = image.copy()
                image[mask_bool] = fill

        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image
        image_pil = Image.fromarray(image_rgb)

        if mask.max() <= 1.0:
            logger.debug("Scaling mask from 0-1 to 0-255")
            mask = (mask * 255).astype(np.uint8)
        mask_pil = Image.fromarray(mask).convert("L")

        lama_model = _load_simple_lama()
        logger.debug("Running LaMa inpainting model")
        result_pil = lama_model(image_pil, mask_pil)
        logger.info("LaMa inpainting completed successfully")

        result_rgb = np.array(result_pil)
        if result_rgb.dtype == np.float32 or result_rgb.dtype == np.float64:
            if result_rgb.max() <= 1.0:
                result_rgb = (np.clip(result_rgb, 0, 1) * 255).astype(np.uint8)
        if len(result_rgb.shape) == 3 and result_rgb.shape[2] == 3:
            result_np = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)
        else:
            result_np = result_rgb
        return result_np
