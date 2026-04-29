from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class SegmentationRoutingStrategy(ABC):
    """Abstract Strategy for choosing how SAM should be invoked.

    A routing strategy inspects the click location, the depth map and the RGB
    image, then returns a context dict that drives the next SAM call:

    - ``input_image``: which array to feed SAM (RGB or adapted depth).
    - ``expand_pixels``: dilation to apply to the resulting mask.
    - ``sd_strength``: Stable Diffusion strength to forward to inpainting.
    - ``use_broad_mask``: hint to prefer SAM's broader mask candidate.
    """

    @abstractmethod
    def choose_input(
        self,
        rgb_image: np.ndarray,
        raw_depth: np.ndarray,
        adapted_depth: np.ndarray,
        x: int,
        y: int,
    ) -> dict[str, Any]:
        raise NotImplementedError
