from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from ....utils.debug_image_saver import DebugImageSaver
from ..image_inpainting_strategy import ImageInpaintingStrategy
from .lama_inpainting_strategy import LamaInpaintingStrategy
from .stable_diffusion_inpainting_strategy import StableDiffusionInpaintingStrategy

logger = logging.getLogger(__name__)


class HybridInpaintingStrategy(ImageInpaintingStrategy):
    """Two-stage inpainting strategy that composes LaMa + Stable Diffusion.

    Phase 1 (LaMa): cheap structural removal that avoids hallucinating new
    content. Phase 2 (SD, optional): texture refinement at low ``strength``
    so reimagined edges blend with surroundings without inventing furniture.

    Both phases are themselves :class:`ImageInpaintingStrategy` instances
    injected at construction, so the composition is itself a Strategy
    (callers can swap in different LaMa or SD variants without modifying
    this class).
    """

    SD_SKIP_THRESHOLD: float = 0.2
    SHARPEN_SIGMA: float = 0.8
    SHARPEN_AMOUNT: float = 0.6

    def __init__(
        self,
        primary: ImageInpaintingStrategy | None = None,
        refiner: ImageInpaintingStrategy | None = None,
    ) -> None:
        logger.info("Initializing Hybrid Inpainting Pipeline...")
        self._primary: ImageInpaintingStrategy = primary or LamaInpaintingStrategy()
        self._refiner: ImageInpaintingStrategy = refiner or StableDiffusionInpaintingStrategy()
        self._image_saver = DebugImageSaver()
        logger.info("Hybrid Pipeline initialized successfully.")

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
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

        logger.info("--- Hybrid Pipeline Phase 1: Structural removal (LaMa) ---")
        primary_result = self._primary.inpaint(image, mask)
        self._image_saver.save("debug_lama_output", primary_result)

        logger.info("--- Hybrid Pipeline Phase 2: Texture refinement (SD) ---")
        refiner_kwargs = kwargs.copy()
        dynamic_strength = float(kwargs.get("strength", 0.35))
        refiner_kwargs["strength"] = dynamic_strength
        logger.info(f"Using dynamic SD strength: {dynamic_strength}")

        # Skip the SD pass when strength is very low - it adds smear and
        # can hallucinate objects without contributing meaningful detail.
        if dynamic_strength <= self.SD_SKIP_THRESHOLD:
            final_result = primary_result.copy()
            logger.info("Skipping SD (strength <= 0.2); using primary result only.")
        else:
            final_result = self._refiner.inpaint(primary_result, mask, **refiner_kwargs)

        # Re-align result/mask before any boolean indexing.
        if final_result.shape[:2] != image.shape[:2]:
            final_result = cv2.resize(
                final_result,
                (image.shape[1], image.shape[0]),
                interpolation=cv2.INTER_LANCZOS4,
            )
        if mask.shape[:2] != final_result.shape[:2]:
            mask = cv2.resize(
                mask,
                (final_result.shape[1], final_result.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
            thresh = 0.5 if mask.max() <= 1.0 else 127
            mask = (mask > thresh).astype(np.uint8) * 255

        # Unsharp mask: pulls reimagined edges toward surrounding contrast.
        blurred = cv2.GaussianBlur(final_result, (0, 0), self.SHARPEN_SIGMA)
        as_float = final_result.astype(np.float32)
        final_result = np.clip(
            as_float + self.SHARPEN_AMOUNT * (as_float - blurred.astype(np.float32)),
            0,
            255,
        ).astype(np.uint8)

        # Color-nudge the mask interior toward the boundary mean. We avoid
        # touching the dilated edge band so reimagined geometry isn't warped.
        mask_bool = (mask > 127) if (mask.dtype == np.uint8 or mask.max() > 1) else (mask > 0.5)
        if mask_bool.any() and len(final_result.shape) == 3:
            mask_uint = (mask * 255).astype(np.uint8) if mask.max() <= 1 else mask.astype(np.uint8)
            kernel = np.ones((3, 3), np.uint8)
            boundary = (cv2.dilate(mask_uint, kernel) > 0) & (~mask_bool)
            interior_only = cv2.erode(mask_uint, np.ones((7, 7), np.uint8)) > 127
            if boundary.any() and interior_only.any():
                boundary_mean = final_result[boundary].mean(axis=0)
                inside_mean = final_result[interior_only].mean(axis=0)
                shift = (boundary_mean.astype(np.float32) - inside_mean.astype(np.float32)) * 0.35
                out = final_result.astype(np.float32)
                out[interior_only] = np.clip(out[interior_only] + shift, 0, 255)
                final_result = out.astype(np.uint8)

        self._image_saver.save("debug_sd_output", final_result)
        logger.info("Hybrid Pipeline completed successfully.")
        return final_result
