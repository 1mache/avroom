# src/routing/topographic_routing_strategy.py
import numpy as np
import logging
from core.interfaces import ISegmentationRoutingStrategy

logger = logging.getLogger(__name__)

class TopographicRoutingStrategy(ISegmentationRoutingStrategy):
    def __init__(self, min_ratio: float = 0.05, max_ratio: float = 0.15, 
                 topo_range_thresh: float = 0.08, protrusion_thresh: float = 0.04):
        # HARDCODED PARAMETERS (Now exposed and logged)
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio
        self.topo_range_thresh = topo_range_thresh
        self.protrusion_thresh = protrusion_thresh
        
        logger.info("="*50)
        logger.info("INITIALIZING TOPOGRAPHIC ROUTER WITH PARAMETERS:")
        logger.info(f" - Window Min Ratio: {self.min_ratio}")
        logger.info(f" - Window Max Ratio: {self.max_ratio}")
        logger.info(f" - Topo Range Threshold: {self.topo_range_thresh}")
        logger.info(f" - Protrusion Threshold: {self.protrusion_thresh}")
        logger.info("="*50)

    def choose_input(self, rgb_image: np.ndarray, raw_depth: np.ndarray, adapted_depth: np.ndarray, x: int, y: int) -> dict:
        h, w = raw_depth.shape[:2]
        base_image_size = min(h, w)

        pixel_depth = raw_depth[y, x, 0] if len(raw_depth.shape) == 3 else raw_depth[y, x]
        depth_ratio = float(pixel_depth) / 255.0

        # Dynamic local window around click point.
        # Near points get a larger neighborhood because their object footprint is usually larger.
        min_window = int(base_image_size * self.min_ratio)
        max_window = int(base_image_size * self.max_ratio)
        dynamic_window_size = int(min_window + depth_ratio * (max_window - min_window))
        
        half_w = dynamic_window_size // 2
        x_min, x_max = max(0, x - half_w), min(w, x + half_w)
        y_min, y_max = max(0, y - half_w), min(h, y + half_w)

        depth_window = raw_depth[y_min:y_max, x_min:x_max, 0] if len(raw_depth.shape) == 3 else raw_depth[y_min:y_max, x_min:x_max]
        
        norm_window = depth_window.astype(float) / 255.0
        norm_center = float(pixel_depth) / 255.0

        topo_range = np.max(norm_window) - np.min(norm_window)

        # 10th percentile approximates a conservative background baseline
        # inside the local window (often floor/wall behind the object).
        background_baseline = np.percentile(norm_window, 10)
        protrusion = abs(norm_center - background_baseline)

        logger.info(f"[ROUTER DECISION] Topography at ({x}, {y}) -> Range: {topo_range:.3f} (Threshold: {self.topo_range_thresh}), Protrusion: {protrusion:.3f} (Threshold: {self.protrusion_thresh})")

        # Decision rule:
        # Treat as 3D if either local topography is rough OR center protrudes from local background.
        is_3d_object = (topo_range > self.topo_range_thresh) or (protrusion > self.protrusion_thresh)

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
            # Detailed logging to debug WHICH condition triggered the OR gate
            trigger_reasons = []
            if topo_range > self.topo_range_thresh: trigger_reasons.append("High Topo Range")
            if protrusion > self.protrusion_thresh: trigger_reasons.append("High Protrusion")
            
            logger.info(f"[ROUTER DECISION] Classified as: 3D Object (Furniture/Pouf). Triggered by: {' OR '.join(trigger_reasons)}")
            
            context['input_image'] = adapted_depth
            context['sd_strength'] = 0.85  
            context['use_broad_mask'] = True 
            context['expand_pixels'] = int(30 + (depth_ratio * 60)) 

        logger.info(f"[ROUTER OUTPUT] Expand={context['expand_pixels']}px, SD_Strength={context['sd_strength']}, BroadMask={context['use_broad_mask']}")
        return context