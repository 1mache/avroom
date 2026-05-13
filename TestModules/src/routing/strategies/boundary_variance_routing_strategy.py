from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from ...ai_engines.segmentation.image_segmentation_facade import ImageSegmentationFacade
from ..segmentation_routing_strategy import SegmentationRoutingStrategy

logger = logging.getLogger(__name__)


class BoundaryVarianceRoutingStrategy(SegmentationRoutingStrategy):
    """Decide expansion parameters by measuring depth variance on a thin
    "boundary ring" around a probe SAM mask.

    Logic:

    1. Ask SAM (via the injected segmentation facade) for a tight probe mask.
    2. Dilate it by ~7 px and subtract the original mask, leaving only the
       outer boundary band (the immediate neighborhood around the object).
    3. Compute depth variance over that band. High variance = uneven local
       geometry around the object, so we treat it as a 3D object and apply
       a slightly larger expansion. Low variance = flat surface (TV, window,
       picture) - a tight band is enough.

    The strategy receives the segmentation facade by DI; this is the only
    cross-domain dependency in the pipeline and exists because the router
    needs SAM to probe before deciding how to invoke SAM "for real".
    """

    DEFAULT_BOUNDARY_VAR_THRESH: float = 0.005

    def __init__(
        self,
        segmentation_facade: ImageSegmentationFacade,
        boundary_var_thresh: float = DEFAULT_BOUNDARY_VAR_THRESH,
    ) -> None:
        self._segmentation = segmentation_facade
        self._boundary_var_thresh = boundary_var_thresh
        logger.info(
            f"Initialized BoundaryVarianceRoutingStrategy (Thresh: {boundary_var_thresh})"
        )

    def choose_input(
        self,
        rgb_image: np.ndarray,
        raw_depth: np.ndarray,
        adapted_depth: np.ndarray,
        x: int,
        y: int,
    ) -> dict[str, Any]:
        h, w = raw_depth.shape[:2]

        pixel_depth = raw_depth[y, x, 0] if len(raw_depth.shape) == 3 else raw_depth[y, x]
        depth_ratio = float(pixel_depth) / 255.0

        # Probe mask - tight, never broad, so we don't grab nearby objects.
        logger.info(f"Fetching probe mask at ({x}, {y}) for Boundary Analysis...")
        probe_mask, _ = self._segmentation.get_mask_at_point(
            adapted_depth, x, y, expand_pixels=0, use_broad_mask=False
        )
        if probe_mask.shape[:2] != (h, w):
            probe_mask = cv2.resize(probe_mask, (w, h), interpolation=cv2.INTER_NEAREST)

        mask_uint8 = probe_mask.astype(np.uint8)

        # 7px ring around the probe mask (outer boundary band only).
        kernel = np.ones((7, 7), np.uint8)
        dilated_mask = cv2.dilate(mask_uint8, kernel, iterations=1)
        boundary_ring = dilated_mask - mask_uint8

        norm_depth = raw_depth.astype(float) / 255.0
        if len(norm_depth.shape) == 3:
            norm_depth = norm_depth[:, :, 0]

        boundary_depths = norm_depth[boundary_ring > 0]

        if len(boundary_depths) == 0:
            boundary_variance: float = 0.0
        else:
            boundary_variance = float(np.var(boundary_depths))

        logger.info(
            f"[ROUTER] Boundary Variance -> {boundary_variance:.5f} "
            f"(Thresh: {self._boundary_var_thresh})"
        )

        is_3d_object = boundary_variance > self._boundary_var_thresh

        # Tighter base bands than the legacy strategies; the post-pipeline
        # uniform 3 px dilation handles the last few edge pixels.
        if is_3d_object:
            base_expand = 10
            extra_expand = int(depth_ratio * 10)
        else:
            base_expand = 4
            extra_expand = int(depth_ratio * 6)

        expand_pixels = base_expand + extra_expand

        context: dict[str, Any] = {
            "input_image": adapted_depth,
            "sd_strength": 0.35,
            "use_broad_mask": False,
            "expand_pixels": expand_pixels,
        }

        logger.info(
            "[ROUTER] Decision: "
            f"{'3D Object' if is_3d_object else 'Flat Surface'} | Output: {context}"
        )
        return context
