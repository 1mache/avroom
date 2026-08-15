from __future__ import annotations

import logging

import numpy as np

from .inpaint_sd_params import InpaintSdParams
from .inpainting_verification_result import InpaintingVerificationResult
from .inpainting_verification_strategy import InpaintingVerificationStrategy
from .strategies.gemini_inpainting_verification_strategy import (
    GeminiInpaintingVerificationStrategy,
)

logger = logging.getLogger(__name__)


class InpaintingVerificationFacade:
    """Public entry point for post-inpaint quality checks.

    Holds exactly one :class:`InpaintingVerificationStrategy`. Default is
    Gemini (CLIP fallback when the API key is a placeholder).
    """

    def __init__(self, strategy: InpaintingVerificationStrategy | None = None) -> None:
        self._strategy: InpaintingVerificationStrategy = (
            strategy or GeminiInpaintingVerificationStrategy()
        )
        logger.info(
            "InpaintingVerificationFacade ready (strategy=%s)",
            type(self._strategy).__name__,
        )

    @property
    def strategy(self) -> InpaintingVerificationStrategy:
        return self._strategy

    def verify(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
    ) -> InpaintingVerificationResult:
        """Run verification on a BGR inpaint candidate."""
        return self._strategy.verify(image, mask, params)
