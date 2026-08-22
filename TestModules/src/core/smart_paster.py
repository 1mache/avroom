from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .cutout_rescaler import DepthRescaleResult, compute_depth_rescale

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmartPasteResult:
    """Outcome of smart paste before persistence."""

    source_average_depth: float
    target_depth: float
    scale_factor: float


class SmartPaster:
    """Orchestrates post-drop object adjustments for smart paste.

    Today: depth-proportional rescale only.
    Future: auto-rotate after rescale.
    """

    def smart_paste(
        self,
        *,
        source_average_depth: float,
        depth_map: np.ndarray,
        x: int,
        y: int,
    ) -> SmartPasteResult:
        """Run smart paste at natural-image placement ``(x, y)``."""
        logger.info("Smart paste requested: placement=(%d,%d)", x, y)
        depth_result = self._compute_depth_rescale(
            source_average_depth=source_average_depth,
            depth_map=depth_map,
            x=x,
            y=y,
        )
        # ponytail: wire NovelView auto-rotate here when implemented
        return SmartPasteResult(
            source_average_depth=depth_result.source_average_depth,
            target_depth=depth_result.target_depth,
            scale_factor=depth_result.scale_factor,
        )

    def _compute_depth_rescale(
        self,
        source_average_depth: float,
        depth_map: np.ndarray,
        x: int,
        y: int,
    ) -> DepthRescaleResult:
        return compute_depth_rescale(
            source_average_depth=source_average_depth,
            depth_map=depth_map,
            x=x,
            y=y,
        )
