from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class _SingleEntryCache:
    """Tiny single-entry key/value cache used by :class:`SamImageAdapter`.

    Kept as a separate class so that the cache concern is composed in, not
    inherited - and so a caller could swap it for a richer cache (LRU, file-
    backed, etc.) without touching the adapter logic.
    """

    def __init__(self) -> None:
        self._cache_key: str | None = None
        self._cached_data: Any = None

    def get(self, key: str) -> Any:
        if self._cache_key == key:
            return self._cached_data
        return None

    def set(self, key: str, data: Any) -> None:
        self._cache_key = key
        self._cached_data = data


class SamImageAdapter:
    """Convert a depth map into the 3-channel RGB array SAM expects as input.

    Why this exists: SAM was trained on natural RGB images and over-segments
    on fabric creases, shadows, and texture. Feeding it the depth map instead
    forces it to reason about geometry rather than appearance, which yields
    much cleaner masks for object removal.

    Adapted images are cached by ``(image_id, point)``, so the most common
    flow - probe-then-final SAM call at the same click - only adapts once.
    """

    def __init__(self) -> None:
        self._cache = _SingleEntryCache()
        logger.info("SamImageAdapter initialized")

    def get_adapted_image(
        self,
        raw_data: Any,
        image_id: str,
        point: tuple[int, int],
    ) -> np.ndarray:
        cache_key = f"{image_id}_{point[0]}_{point[1]}"

        cached_image = self._cache.get(cache_key)
        if cached_image is not None:
            logger.info("Using cached adapted image")
            return cached_image

        logger.info("Adapting new data for SAM and caching it...")

        adapted = np.array(raw_data)

        if len(adapted.shape) == 2:
            logger.debug("Converting grayscale depth to RGB")
            adapted = cv2.cvtColor(adapted, cv2.COLOR_GRAY2RGB)
        elif len(adapted.shape) == 3 and adapted.shape[2] == 4:
            logger.debug("Converting RGBA to RGB")
            adapted = cv2.cvtColor(adapted, cv2.COLOR_RGBA2RGB)

        self._cache.set(cache_key, adapted)
        logger.debug(f"Adapted image cached with key: {cache_key}")

        return adapted
