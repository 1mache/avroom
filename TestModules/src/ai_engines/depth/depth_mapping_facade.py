from __future__ import annotations

import logging

import numpy as np

from .depth_mapping_strategy import DepthMappingStrategy
from .strategies.near_far_blended_depth_mapping_strategy import (
    NearFarBlendedDepthMappingStrategy,
)

logger = logging.getLogger(__name__)


class DepthMappingFacade:
    """Public entry point for depth-map generation.

    Holds exactly one :class:`DepthMappingStrategy` and delegates to it. The
    strategy can be swapped at construction time without any client code
    needing to know which model is in use.
    """

    def __init__(self, strategy: DepthMappingStrategy | None = None) -> None:
        self._strategy: DepthMappingStrategy = strategy or NearFarBlendedDepthMappingStrategy()
        logger.info(
            f"DepthMappingFacade ready (strategy={type(self._strategy).__name__})"
        )

    @property
    def strategy(self) -> DepthMappingStrategy:
        return self._strategy

    def map_depth(self, image: np.ndarray) -> np.ndarray:
        """Return a depth map for ``image`` produced by the active strategy."""
        return self._strategy.map_depth(image)
