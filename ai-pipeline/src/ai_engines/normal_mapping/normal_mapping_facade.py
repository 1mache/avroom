from __future__ import annotations

import logging

import numpy as np

from .normal_mapping_strategy import NormalMappingStrategy
from .strategies.metric3d_normal_mapping_strategy import Metric3DNormalMappingStrategy

logger = logging.getLogger(__name__)


class NormalMappingFacade:
    """Public entry point for per-pixel surface-normal generation.

    Holds exactly one :class:`NormalMappingStrategy` and delegates to it. The
    strategy can be swapped at construction time without client code knowing
    which model is in use.
    """

    def __init__(self, strategy: NormalMappingStrategy | None = None) -> None:
        self._strategy: NormalMappingStrategy = strategy or Metric3DNormalMappingStrategy()
        logger.info(
            "NormalMappingFacade ready (strategy=%s)",
            type(self._strategy).__name__,
        )

    @property
    def strategy(self) -> NormalMappingStrategy:
        return self._strategy

    def map_normals(self, image: np.ndarray) -> np.ndarray:
        """Return camera-frame unit normals for ``image`` from the active strategy."""
        return self._strategy.map_normals(image)
