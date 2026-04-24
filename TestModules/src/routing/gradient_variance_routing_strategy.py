# src/routing/gradient_variance_routing_strategy.py
import cv2
import numpy as np
import logging
from ..core.interfaces import ISegmentationRoutingStrategy

logger = logging.getLogger(__name__)

class GradientVarianceRoutingStrategy(ISegmentationRoutingStrategy):
    """
    Analyzes the variance of the depth gradient (surface normals) rather than raw depth.
    Flat surfaces have constant gradients (zero variance). 
    Curved 3D objects have changing gradients (high variance).
    """
    def __init__(self, min_ratio: float = 0.05, max_ratio: float = 0.15, gradient_var_thresh: float = 0.002):
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio
        self.gradient_var_thresh = gradient_var_thresh
        logger.info(f"Initialized GradientVarianceRoutingStrategy (Thresh: {gradient_var_thresh})")

    def choose_input(self, rgb_image: np.ndarray, raw_depth: np.ndarray, adapted_depth: np.ndarray, x: int, y: int) -> dict:
        h, w = raw_depth.shape[:2]
        base_image_size = min(h, w)
        
        pixel_depth = raw_depth[y, x, 0] if len(raw_depth.shape) == 3 else raw_depth[y, x]
        depth_ratio = float(pixel_depth) / 255.0

        # Dynamic window sizing:
        # closer click -> larger window, farther click -> smaller window.
        # This keeps local analysis proportional to perceived object scale.
        min_window = int(base_image_size * self.min_ratio)
        max_window = int(base_image_size * self.max_ratio)
        dynamic_window_size = int(min_window + depth_ratio * (max_window - min_window))
        
        half_w = dynamic_window_size // 2
        x_min, x_max = max(0, x - half_w), min(w, x + half_w)
        y_min, y_max = max(0, y - half_w), min(h, y + half_w)

        depth_window = raw_depth[y_min:y_max, x_min:x_max, 0] if len(raw_depth.shape) == 3 else raw_depth[y_min:y_max, x_min:x_max]
        norm_window = depth_window.astype(float) / 255.0

        # Compute depth derivatives with Sobel.
        # Flat regions keep similar gradients; curved/structured regions vary more.
        grad_x = cv2.Sobel(norm_window, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(norm_window, cv2.CV_64F, 0, 1, ksize=3)
        
        # Calculate gradient magnitude
        magnitude = cv2.magnitude(grad_x, grad_y)
        
        # Core signal: variance of gradient magnitude.
        # High variance usually indicates non-flat geometry.
        grad_variance = np.var(magnitude)
        
        logger.info(f"[ROUTER] Gradient Variance at ({x}, {y}) -> {grad_variance:.5f} (Thresh: {self.gradient_var_thresh})")
        
        is_3d_object = grad_variance > self.gradient_var_thresh

        context = {
            'input_image': adapted_depth if is_3d_object else rgb_image,
            'sd_strength': 0.85 if is_3d_object else 0.50,
            'use_broad_mask': is_3d_object,
            'expand_pixels': int(30 + (depth_ratio * 60)) if is_3d_object else int(10 + (depth_ratio * 20))
        }

        logger.info(f"[ROUTER] Decision: {'3D Object' if is_3d_object else 'Flat Surface'} | Output: {context}")
        return context
