from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from ...ai_engines.segmentation.image_segmentation_facade import ImageSegmentationFacade
from ..segmentation_routing_strategy import SegmentationRoutingStrategy

logger = logging.getLogger(__name__)


class CenterOfMassRoutingStrategy(SegmentationRoutingStrategy):
    """Compare the median depth of the probe mask against the median depth
    of an immediately surrounding "padding box".

    Strong protrusion above the local floor/wall implies a 3D object; small
    protrusion implies a flat surface (TV, window, picture frame). The
    decision drives how aggressively to expand the SAM mask and how much
    Stable Diffusion strength to forward to inpainting.
    """

    DEFAULT_PROTRUSION_THRESH: float = 0.03

    def __init__(
        self,
        segmentation_facade: ImageSegmentationFacade,
        protrusion_thresh: float = DEFAULT_PROTRUSION_THRESH,
    ) -> None:
        self._segmentation = segmentation_facade
        self._protrusion_thresh = protrusion_thresh
        logger.info(
            "Initialized CenterOfMassRoutingStrategy "
            f"(protrusion_thresh={protrusion_thresh})"
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

        logger.info(
            f"Router self-fetching PROBE mask at ({x}, {y}) for Center of Mass analysis..."
        )
        probe_mask, _ = self._segmentation.get_mask_at_point(
            adapted_depth, x, y, expand_pixels=0, use_broad_mask=True
        )
        if probe_mask.shape[:2] != (h, w):
            probe_mask = cv2.resize(probe_mask, (w, h), interpolation=cv2.INTER_NEAREST)

        y_indices, x_indices = np.where(probe_mask > 0)
        if len(y_indices) == 0:
            return {
                "input_image": rgb_image,
                "expand_pixels": 15,
                "sd_strength": 0.5,
                "use_broad_mask": False,
            }

        y_min, y_max = int(np.min(y_indices)), int(np.max(y_indices))
        x_min, x_max = int(np.min(x_indices)), int(np.max(x_indices))

        obj_h = y_max - y_min
        obj_w = x_max - x_min
        pad_y = max(20, int(obj_h * 0.2))
        pad_x = max(20, int(obj_w * 0.2))

        box_y_min, box_y_max = max(0, y_min - pad_y), min(h, y_max + pad_y)
        box_x_min, box_x_max = max(0, x_min - pad_x), min(w, x_max + pad_x)

        depth_window = raw_depth[box_y_min:box_y_max, box_x_min:box_x_max]
        if len(depth_window.shape) == 3:
            depth_window = depth_window[:, :, 0]
        mask_window = probe_mask[box_y_min:box_y_max, box_x_min:box_x_max]

        norm_depth_window = depth_window.astype(float) / 255.0

        # Medians are robust to outlier pixels in noisy depth maps.
        object_pixels = norm_depth_window[mask_window > 0]
        background_pixels = norm_depth_window[mask_window == 0]

        object_median = float(np.median(object_pixels)) if len(object_pixels) > 0 else 0.0
        bg_median = float(np.median(background_pixels)) if len(background_pixels) > 0 else 0.0

        protrusion = abs(object_median - bg_median)

        logger.info(
            f"[ROUTER] Center of Mass -> object_med={object_median:.3f} "
            f"bg_med={bg_median:.3f} protrusion={protrusion:.3f} "
            f"(thresh={self._protrusion_thresh})"
        )

        is_3d_object = protrusion > self._protrusion_thresh

        context: dict[str, Any] = {
            "input_image": None,
            "expand_pixels": 0,
            "sd_strength": 0.0,
            "use_broad_mask": False,
        }

        if not is_3d_object:
            logger.info("[ROUTER] Classified as: Flat Surface (Wall/Window/TV)")
            context["input_image"] = rgb_image
            context["sd_strength"] = 0.50
            context["use_broad_mask"] = False
            context["expand_pixels"] = int(10 + (depth_ratio * 20))
        else:
            logger.info("[ROUTER] Classified as: 3D Object (Furniture/Pouf)")
            context["input_image"] = adapted_depth
            context["sd_strength"] = 0.85
            context["use_broad_mask"] = True
            context["expand_pixels"] = int(30 + (depth_ratio * 60))

        logger.info(
            f"[ROUTER OUTPUT] Expand={context['expand_pixels']}px "
            f"SD_Strength={context['sd_strength']} BroadMask={context['use_broad_mask']}"
        )
        return context
