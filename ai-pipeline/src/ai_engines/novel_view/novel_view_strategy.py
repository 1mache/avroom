from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from PIL import Image


class NovelViewStrategy(ABC):
    """Abstract Strategy for novel-view synthesis (image + pose → 2D image).

    Implementations take a segmented object cutout (anything :func:`to_pil_rgba`
    can normalize) and return a uint8 BGRA array representing the same object
    from a requested camera viewpoint. Mesh-aware strategies may also accept an
    optional GLB via ``mesh=``.

    Concrete strategies live under
    :mod:`avroom_object_removal.ai_engines.novel_view.strategies`.
    """

    @abstractmethod
    def synthesize(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        elevation_deg: float,
        azimuth_deg: float,
        relative_elevation_deg: float = 0.0,
        radius: float = 0.0,
        seed: int = 0,
        mesh: bytes | Path | str | None = None,
    ) -> np.ndarray:
        """Synthesize a novel view of ``image`` at the requested camera pose.

        Args:
            image: Object cutout (RGBA preferred). Not the full room photo.
            elevation_deg: Absolute elevation of the **source** view in degrees.
            azimuth_deg: Relative azimuth to the **target** view in degrees.
            relative_elevation_deg: Relative elevation delta to the target view.
            radius: Optional zoom / camera distance (model-specific; 0 = default).
            seed: RNG seed for reproducible generation.
            mesh: Optional GLB mesh (path or bytes). Image-to-image strategies
                ignore this; mesh-render strategies require it (or generate one).

        Returns:
            uint8 ``numpy.ndarray`` of shape ``(H, W, 4)`` in BGRA channel order.
        """
        raise NotImplementedError
