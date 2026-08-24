from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .image_inpainting_strategy import ImageInpaintingStrategy
from .inpaint_params import InpaintParams
from .inpaint_result import InpaintResult
from .strategies.hybrid_inpainting_strategy import HybridInpaintingStrategy

logger = logging.getLogger(__name__)


class ImageInpaintingFacade:
    """Public entry point for masked image inpainting.

    Holds exactly one :class:`ImageInpaintingStrategy`. Default is the hybrid
    LaMa+SD composite; pass any other strategy (e.g. plain LaMa, plain SD,
    or a future Inpaint-Anything strategy) to swap.
    """

    def __init__(self, strategy: ImageInpaintingStrategy | None = None) -> None:
        self._strategy: ImageInpaintingStrategy = strategy or HybridInpaintingStrategy()
        logger.info(
            f"ImageInpaintingFacade ready (strategy={type(self._strategy).__name__})"
        )

    @property
    def strategy(self) -> ImageInpaintingStrategy:
        return self._strategy

    def inpaint(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintParams | None = None,
        *,
        verify_trace: list[dict[str, Any]] | None = None,
    ) -> InpaintResult:
        """Inpaint ``image`` over ``mask`` using the active strategy."""
        return self._strategy.inpaint(image, mask, params, verify_trace=verify_trace)
