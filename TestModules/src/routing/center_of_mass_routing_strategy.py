    # src/routing/center_of_mass_routing_strategy.py
import cv2
import numpy as np
import logging
from ..core.interfaces import ISegmentationRoutingStrategy

logger = logging.getLogger(__name__)

class CenterOfMassRoutingStrategy(ISegmentationRoutingStrategy):
    def __init__(self, sam_facade, protrusion_thresh: float = 0.03):
        # DI: We inject SAM directly into the strategy so it can fetch its own probe mask
        self.sam = sam_facade
        self.protrusion_thresh = protrusion_thresh
        logger.info("Initialized CenterOfMassRoutingStrategy with injected SAM Facade")

    # The Interface signature REMAINS EXACTLY THE SAME! No 'probe_mask' parameter here.
    def choose_input(self, rgb_image: np.ndarray, raw_depth: np.ndarray, adapted_depth: np.ndarray, x: int, y: int) -> dict:
        h, w = raw_depth.shape[:2]
        pixel_depth = raw_depth[y, x, 0] if len(raw_depth.shape) == 3 else raw_depth[y, x]
        depth_ratio = float(pixel_depth) / 255.0

        # 1. The Strategy fetches its own probe mask independently!
        logger.info(f"Router self-fetching PROBE mask at ({x}, {y}) for Center of Mass analysis...")
        probe_mask = self.sam.get_mask_at_point(
            adapted_depth, x, y, expand_pixels=0, use_broad_mask=True
        )
        if probe_mask.shape[:2] != (h, w):
            probe_mask = cv2.resize(probe_mask, (w, h), interpolation=cv2.INTER_NEAREST)

        # 2. Find the bounding box of the probe mask (the entire object)
        y_indices, x_indices = np.where(probe_mask > 0)
        if len(y_indices) == 0:
            return {'input_image': rgb_image, 'expand_pixels': 15, 'sd_strength': 0.5, 'use_broad_mask': False}

        y_min, y_max = np.min(y_indices), np.max(y_indices)
        x_min, x_max = np.min(x_indices), np.max(x_indices)

        # 3. Expand the object's bounding box to include nearby background.
        # We compare object depth against immediate surroundings (floor/wall near it),
        # not against the full image, to avoid unrelated depth noise.
        obj_h = y_max - y_min
        obj_w = x_max - x_min
        pad_y = max(20, int(obj_h * 0.2))
        pad_x = max(20, int(obj_w * 0.2))

        box_y_min, box_y_max = max(0, y_min - pad_y), min(h, y_max + pad_y)
        box_x_min, box_x_max = max(0, x_min - pad_x), min(w, x_max + pad_x)

        # 4. Extract depth and mask windows
        depth_window = raw_depth[box_y_min:box_y_max, box_x_min:box_x_max]
        if len(depth_window.shape) == 3:
            depth_window = depth_window[:, :, 0]
        mask_window = probe_mask[box_y_min:box_y_max, box_x_min:box_x_max]

        norm_depth_window = depth_window.astype(float) / 255.0

        # 5. Compare object depth to local background depth.
        # Median is used because it is robust to outliers and noisy pixels.
        object_pixels = norm_depth_window[mask_window > 0]
        background_pixels = norm_depth_window[mask_window == 0]

        object_median = np.median(object_pixels) if len(object_pixels) > 0 else 0
        bg_median = np.median(background_pixels) if len(background_pixels) > 0 else 0

        protrusion = abs(object_median - bg_median)
        
        logger.info(f"[ROUTER DECISION] Center of Mass Analysis -> Object Median Depth: {object_median:.3f}, BG Median Depth: {bg_median:.3f}")
        logger.info(f"[ROUTER DECISION] Protrusion: {protrusion:.3f} (Threshold: {self.protrusion_thresh})")

        is_3d_object = protrusion > self.protrusion_thresh

        # === DYNAMIC CONTEXT GENERATION ===
        context = {
            'input_image': None,
            'expand_pixels': 0,
            'sd_strength': 0.0,
            'use_broad_mask': False
        }

        if not is_3d_object:
            logger.info("[ROUTER DECISION] Classified as: Flat Surface (Wall/Window/TV)")
            context['input_image'] = rgb_image
            context['sd_strength'] = 0.50  
            context['use_broad_mask'] = False 
            context['expand_pixels'] = int(10 + (depth_ratio * 20))
        else:
            logger.info("[ROUTER DECISION] Classified as: 3D Object (Furniture/Pouf)")
            context['input_image'] = adapted_depth
            context['sd_strength'] = 0.85  
            context['use_broad_mask'] = True 
            context['expand_pixels'] = int(30 + (depth_ratio * 60)) 

        logger.info(f"[ROUTER OUTPUT] Expand={context['expand_pixels']}px, SD_Strength={context['sd_strength']}, BroadMask={context['use_broad_mask']}")
        return context
