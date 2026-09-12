from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class DepthMappingStrategy(ABC):
    """Abstract Strategy for producing a depth map from a BGR image.

    Implementations are responsible for picking a model, loading its weights
    (lazily, see ``functools.lru_cache`` patterns in the concrete strategies),
    and returning a single-channel depth map as a uint8 numpy array.
    """

    @abstractmethod
    def map_depth(self, image: np.ndarray) -> np.ndarray:
        """Compute a depth map for ``image``.

        Args:
            image: Input image as a numpy array (BGR or RGB; implementations
                must accept BGR since that is what the pipeline carries).

        Returns:
            A 2-D ``uint8`` depth map where higher values are closer to the
            camera and lower values are farther.
        """
        raise NotImplementedError
