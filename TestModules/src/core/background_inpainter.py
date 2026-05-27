from __future__ import annotations

import logging

import numpy as np

from ..ai_engines.inpainting.image_inpainting_facade import ImageInpaintingFacade
from ..utils.debug_image_saver import DebugImageSaver

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

    def __init__(
        self,
        inpainting_facade: ImageInpaintingFacade | None = None,
        debug_image_saver: DebugImageSaver | None = None,
    ) -> None:
        self.inpainting: ImageInpaintingFacade = (
            inpainting_facade or ImageInpaintingFacade()
        )
        self.image_saver: DebugImageSaver = debug_image_saver or DebugImageSaver()
        logger.info("BackgroundInpainter initialized")

    def cut_mask_from_image(
        self,
        original_image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """Inpaint the masked region and return the reconstructed background.

        Delegates directly to :meth:`ImageInpaintingFacade.inpaint`. The
        inpainting strategy (default: :class:`HybridInpaintingStrategy`) uses
        LaMa for structural fill and optionally Stable Diffusion for texture
        refinement, matching step 4 of :meth:`ObjectRemover.remove_object`.

        Args:
            original_image: BGR ``np.ndarray`` of the full scene. Must match
                the spatial dimensions of ``mask``.
            mask: Binary 2-D mask (0 background / 255 foreground) indicating
                which pixels to replace. Typically one of the ``refined_mask``
                values returned by
                :meth:`ObjectSegmentor.get_mask_for_object_at_position`.

        Returns:
            A BGR ``np.ndarray`` of the same spatial size as ``original_image``
            with the masked region filled by the inpainting model.
        """
        logger.info("Step 4: Inpainting masked region...")
        result_image = self.inpainting.inpaint(original_image, mask)
        self.image_saver.save("final_removed_object", result_image)
        logger.info("Inpainting completed successfully")
        return result_image
