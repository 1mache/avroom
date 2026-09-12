from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class NormalMappingStrategy(ABC):
    """Abstract Strategy for producing a per-pixel surface-normal map from a BGR image.

    Implementations load a geometric model (lazily) and return camera-frame
    unit normals as float32 HxWx3. Used today by the debug vision panel; not
    wired into ObjectRemover / smart paste yet.
    """

    @abstractmethod
    def map_normals(self, image: np.ndarray) -> np.ndarray:
        """Compute a surface-normal map for ``image``.

        Args:
            image: BGR ``uint8`` array with shape ``(H, W, 3)`` — the same
                convention the rest of the pipeline carries.

        Returns:
            ``float32`` array of shape ``(H, W, 3)`` with unit vectors
            ``(nx, ny, nz)`` in camera coordinates.
        """
        raise NotImplementedError
