from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from .inpaint_params import InpaintParams
from .inpaint_result import InpaintResult


class ImageInpaintingStrategy(ABC):
    """Abstract Strategy for masked image inpainting.

    Implementations remove the masked region from ``image`` and fill it with
    plausible content. Concrete strategies in this package wrap LaMa, Stable
    Diffusion, or compose both.
    """

    @abstractmethod
    def inpaint(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintParams | None = None,
        *,
        verify_trace: list[dict[str, Any]] | None = None,
    ) -> InpaintResult:
        """Inpaint the masked region of ``image``.

        Args:
            image: Source image in BGR (OpenCV) format.
            mask: Binary or 0/255 mask, same H/W as ``image``. Non-zero
                pixels are the region to be replaced.
            params: Strategy knobs (prompt, strength, SD sampling settings).
                ``None`` uses the strategy's own defaults. Ignored by
                strategies that read no knobs (e.g. LaMa).
            verify_trace: Optional list a verifying strategy (Hybrid) appends
                one debug entry to per verification attempt. Caller-owned;
                strategies that don't verify leave it untouched.

        Returns:
            The inpainted image plus any paste-back adjustments a verifier
            made -- see :class:`InpaintResult`.
        """
        raise NotImplementedError
