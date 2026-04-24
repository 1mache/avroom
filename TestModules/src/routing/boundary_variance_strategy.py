import cv2
import numpy as np
import logging
from ..core.interfaces import ISegmentationRoutingStrategy

logger = logging.getLogger(__name__)

class BoundaryVarianceRoutingStrategy(ISegmentationRoutingStrategy):
    """
    Fetches a probe mask from SAM, isolates its outer boundary (immediate background), 
    and calculates depth variance ONLY along that boundary ring.
    """
    def __init__(self, sam_facade, boundary_var_thresh: float = 0.005):
        self.sam = sam_facade
        self.boundary_var_thresh = boundary_var_thresh
        logger.info(f"Initialized BoundaryVarianceRoutingStrategy (Thresh: {boundary_var_thresh})")

    def choose_input(self, rgb_image: np.ndarray, raw_depth: np.ndarray, adapted_depth: np.ndarray, x: int, y: int) -> dict:
        h, w = raw_depth.shape[:2]
        
        pixel_depth = raw_depth[y, x, 0] if len(raw_depth.shape) == 3 else raw_depth[y, x]
        depth_ratio = float(pixel_depth) / 255.0

        # 1. Probe the object using SAM 
        # (use_broad_mask MUST be False here to avoid grabbing background objects)
        logger.info(f"Fetching probe mask at ({x}, {y}) for Boundary Analysis...")
        probe_mask = self.sam.get_mask_at_point(adapted_depth, x, y, expand_pixels=0, use_broad_mask=False)
        if probe_mask.shape[:2] != (h, w):
            probe_mask = cv2.resize(probe_mask, (w, h), interpolation=cv2.INTER_NEAREST)
        
        mask_uint8 = probe_mask.astype(np.uint8)
        
        # 2. Extract a thin ring around the object.
        # We dilate outward, then subtract the original mask, leaving only the outer band.
        # This band is the immediate neighborhood around the object.
        kernel = np.ones((7, 7), np.uint8) # 7px ring thickness
        dilated_mask = cv2.dilate(mask_uint8, kernel, iterations=1)
        boundary_ring = dilated_mask - mask_uint8
        
        # 3. Read depth values only from boundary-ring pixels.
        # If this ring has mixed depth values, the local area is likely 3D and non-flat.
        norm_depth = raw_depth.astype(float) / 255.0
        if len(norm_depth.shape) == 3:
            norm_depth = norm_depth[:, :, 0]
            
        boundary_depths = norm_depth[boundary_ring > 0]
        
        # 4. Compute depth variance on that ring.
        # High variance means uneven geometry around the object boundary.
        if len(boundary_depths) == 0:
            boundary_variance = 0.0
        else:
            boundary_variance = np.var(boundary_depths)
            
        logger.info(f"[ROUTER] Boundary Variance -> {boundary_variance:.5f} (Thresh: {self.boundary_var_thresh})")
        
        is_3d_object = boundary_variance > self.boundary_var_thresh

        # ==========================================
        # Routing Context Configuration (tuned for tighter masks)
        # ==========================================
        if is_3d_object:
            # 3D objects: slightly larger but still controlled band
            base_expand = 10
            extra_expand = int(depth_ratio * 10)  # up to +10px
        else:
            # Flat objects: very tight band
            base_expand = 4
            extra_expand = int(depth_ratio * 6)   # up to +6px

        expand_pixels = base_expand + extra_expand

        context = {
            'input_image': adapted_depth, # Use adapted depth map for robust SAM behavior.
            'sd_strength': 0.35,       # keep low to avoid SD hallucinating; sharpening is done in post
            'use_broad_mask': False,      # Request a precise object mask only (no broad background grab).
            'expand_pixels': expand_pixels
        }

        logger.info(f"[ROUTER] Decision: {'3D Object' if is_3d_object else 'Flat Surface'} | Output: {context}")
        return context
