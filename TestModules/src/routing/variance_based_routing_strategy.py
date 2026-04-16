# src/routing/variance_based_routing_strategy.py
from core.interfaces import ISegmentationRoutingStrategy
import numpy as np
import logging

logger = logging.getLogger(__name__)

class VarianceBasedRoutingStrategy(ISegmentationRoutingStrategy):
    def __init__(self, variance_threshold: float = 20.0, min_ratio: float = 0.05, max_ratio: float = 0.15):
        self.variance_threshold = variance_threshold
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio

    def choose_input(self, rgb_image: np.ndarray, raw_depth: np.ndarray, adapted_depth: np.ndarray, x: int, y: int) -> dict:
        h, w = raw_depth.shape[:2]
        base_image_size = min(h, w)

        pixel_depth = raw_depth[y, x, 0] if len(raw_depth.shape) == 3 else raw_depth[y, x]
        
        # Depth ratio: 0.0 is furthest (black), 1.0 is closest (white)
        depth_ratio = float(pixel_depth) / 255.0

        # Dynamic local analysis window:
        # use a larger neighborhood for closer clicks to preserve context scale.
        min_window = int(base_image_size * self.min_ratio)
        max_window = int(base_image_size * self.max_ratio)
        dynamic_window_size = int(min_window + depth_ratio * (max_window - min_window))
        
        half_w = dynamic_window_size // 2
        x_min, x_max = max(0, x - half_w), min(w, x + half_w)
        y_min, y_max = max(0, y - half_w), min(h, y + half_w)

        depth_window = raw_depth[y_min:y_max, x_min:x_max, 0] if len(raw_depth.shape) == 3 else raw_depth[y_min:y_max, x_min:x_max]
        variance = np.var(depth_window)
        
        logger.info(f"Context Analysis at ({x}, {y}) -> Depth Ratio: {depth_ratio:.2f}, Variance: {variance:.2f}")

        # === DYNAMIC CONTEXT GENERATION ===
        context = {
            'input_image': None,
            'expand_pixels': 0,
            'sd_strength': 0.0,
            'use_broad_mask': False
        }

        # Low local variance usually means flat surface (wall/screen/window).
        if variance < self.variance_threshold:
            # FLAT SURFACE (Wall, Picture, TV, Window)
            logger.info("Decision: Flat Surface")
            context['input_image'] = rgb_image
            context['sd_strength'] = 0.50  # Gentle blending for walls
            context['use_broad_mask'] = False # ALWAYS False for flat objects to avoid grabbing consoles/frames
            context['expand_pixels'] = int(10 + (depth_ratio * 30)) # Max 40px expansion for flat things
        else:
            # High local variance usually means structured 3D object geometry.
            # 3D OBJECT (Pouf, Sofa, Table)
            logger.info("Decision: 3D Object")
            context['input_image'] = adapted_depth
            context['sd_strength'] = 0.85  # CRITICAL: High strength (85%) completely overwrites dark LaMa stains
            context['use_broad_mask'] = True # Grab the whole volume
            context['expand_pixels'] = int(30 + (depth_ratio * 70)) # Massive expansion (up to 100px) for huge shadows

        logger.info(f"Generated Context: Expand={context['expand_pixels']}px, SD_Strength={context['sd_strength']}, BroadMask={context['use_broad_mask']}")
        return context
