from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from .novel_view_strategy import NovelViewStrategy
from .strategies.stable_zero123_novel_view_strategy import StableZero123NovelViewStrategy

logger = logging.getLogger(__name__)


class NovelViewFacade:
    """Public entry point for novel-view synthesis.

    Holds exactly one :class:`NovelViewStrategy`. The default backend is
    :class:`StableZero123NovelViewStrategy` (``stabilityai/stable-zero123``).
    Pass another concrete strategy at construction to swap backends.
    """

    def __init__(self, strategy: NovelViewStrategy | None = None) -> None:
        self._strategy: NovelViewStrategy = strategy or StableZero123NovelViewStrategy()
        logger.info(
            "NovelViewFacade ready (strategy=%s)",
            type(self._strategy).__name__,
        )

    @property
    def strategy(self) -> NovelViewStrategy:
        return self._strategy

    def synthesize(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        elevation_deg: float,
        azimuth_deg: float,
        relative_elevation_deg: float = 0.0,
        radius: float = 0.0,
        seed: int = 0,
    ) -> np.ndarray:
        """Synthesize a novel 2D view of ``image`` via the active strategy."""

        return self._strategy.synthesize(
            image,
            elevation_deg=elevation_deg,
            azimuth_deg=azimuth_deg,
            relative_elevation_deg=relative_elevation_deg,
            radius=radius,
            seed=seed,
        )
