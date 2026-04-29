from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class ImageInpaintingStrategy(ABC):
    """Abstract Strategy for masked image inpainting.

    Implementations remove the masked region from ``image`` and fill it with
    plausible content. Concrete strategies in this package wrap LaMa, Stable
    Diffusion, or compose both.
    """

    @abstractmethod
    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
        """Inpaint the masked region of ``image``.

        Args:
            image: Source image in BGR (OpenCV) format.
            mask: Binary or 0/255 mask, same H/W as ``image``. Non-zero
                pixels are the region to be replaced.
            **kwargs: Strategy-specific knobs (e.g. ``prompt``, ``strength``
                for diffusion-based variants).

        Returns:
            Inpainted image in BGR format, same H/W as ``image``.
        """
        raise NotImplementedError
