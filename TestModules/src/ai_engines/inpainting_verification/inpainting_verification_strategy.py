from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .inpaint_sd_params import InpaintSdParams
from .inpainting_verification_result import InpaintingVerificationResult


class InpaintingVerificationStrategy(ABC):
    """Abstract Strategy for judging one inpainted candidate.

    Implementations inspect a BGR image, the inpaint mask, and the SD params
    that produced the candidate. Concrete strategies live under
    :mod:`avroom_object_removal.ai_engines.inpainting_verification.strategies`.
    """

    @abstractmethod
    def verify(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
    ) -> InpaintingVerificationResult:
        """Return pass/fail plus a JSON object of params to replay or tweak."""
        raise NotImplementedError
