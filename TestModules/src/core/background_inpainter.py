from __future__ import annotations

import logging
from typing import Final

import numpy as np

from ..ai_engines.inpainting.image_inpainting_facade import ImageInpaintingFacade
from ..utils.debug_image_saver import DebugImageSaver
from ..utils.mask_refiner import MaskRefiner

logger = logging.getLogger(__name__)


class BackgroundInpainter:
    """Inpainting-only facade that fills a masked region in a scene image.

    Executes only step 4 of the full object-removal pipeline: it accepts an
    original BGR image and a binary mask (typically produced by
    :class:`ObjectSegmentor`) and returns the inpainted scene as a BGR array.

    Constructor follows the same dependency-injection pattern used by
    :class:`ObjectRemover` and :class:`ObjectSegmentor`: every collaborator
    has a sensible default so ``BackgroundInpainter()`` works with no
    arguments.

    Primary entry point: :meth:`cut_mask_from_image`.
    """

    COMPOSE_MASK_PADDING_RADIUS: Final[int] = 0

    def __init__(
        self,
        inpainting_facade: ImageInpaintingFacade | None = None,
        debug_image_saver: DebugImageSaver | None = None,
        mask_refiner: MaskRefiner | None = None,
    ) -> None:
        self.inpainting: ImageInpaintingFacade = (
            inpainting_facade or ImageInpaintingFacade()
        )
        self.image_saver: DebugImageSaver = debug_image_saver or DebugImageSaver()
        self.mask_refiner: MaskRefiner = mask_refiner or MaskRefiner()
        logger.info("BackgroundInpainter initialized")

    def _build_compose_mask(
        self,
        inpaint_mask: np.ndarray,
        compose_mask: np.ndarray | None,
    ) -> np.ndarray:
        """Return the mask used to paste inpainted pixels back onto the original."""

        paste_mask = compose_mask if compose_mask is not None else inpaint_mask
        if self.COMPOSE_MASK_PADDING_RADIUS > 0:
            paste_mask = self.mask_refiner.dilate_mask(
                paste_mask,
                pixels=self.COMPOSE_MASK_PADDING_RADIUS,
            )
        return paste_mask

    def cut_mask_from_image(
        self,
        original_image: np.ndarray,
        mask: np.ndarray,
        compose_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        """Inpaint the masked region and return the reconstructed background.

        Delegates to :meth:`ImageInpaintingFacade.inpaint` using ``mask`` (the
        broad inpainting mask), then composes the model output onto
        ``original_image`` using ``compose_mask`` when provided. The compose
        mask is typically the cutout alpha (raw SAM mask), which is tighter than
        ``mask``. Optional padding is controlled by
        :attr:`COMPOSE_MASK_PADDING_RADIUS`.

        The inpainting strategy (default: :class:`HybridInpaintingStrategy`) uses
        LaMa for structural fill and optionally Stable Diffusion for texture
        refinement, matching step 4 of :meth:`ObjectRemover.remove_object`.

        Args:
            original_image: BGR ``np.ndarray`` of the full scene. Must match
                the spatial dimensions of ``mask``.
            mask: Binary 2-D mask (0 background / 255 foreground) passed to
                the inpainting model. Typically one of the ``refined_mask``
                values returned by
                :meth:`ObjectSegmentor.get_mask_for_object_at_position`.
            compose_mask: Optional tighter binary mask for paste-back. When
                omitted, ``mask`` is used for composition as well.

        Returns:
            A BGR ``np.ndarray`` of the same spatial size as ``original_image``.
            Pixels inside the compose mask are taken from the inpainting model
            output; all other pixels are preserved from ``original_image``.
        """
        logger.info("Step 4: Inpainting masked region...")
        result_image = self.inpainting.inpaint(original_image, mask)
        paste_mask = self._build_compose_mask(mask, compose_mask)
        paste_bool = paste_mask > 127
        composed = original_image.copy()
        composed[paste_bool] = result_image[paste_bool]
        self.image_saver.save("final_removed_object", composed)
        logger.info("Inpainting completed successfully")
        return composed
