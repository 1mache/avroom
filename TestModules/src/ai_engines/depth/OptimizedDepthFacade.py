import cv2
import numpy as np
from core.interfaces import IDepthFacade
from ai_engines.depth.ImageDepthMapper import ImageDepthMapper

class OptimizedDepthFacade(IDepthFacade):
    """
    Facade that uses Soft Blending to merge Near and Far models smoothly.
    Returns a clean, un-tampered depth map for optimal data fusion.
    """
    def __init__(self, threshold: int = 100):
        self.depth_mapper = ImageDepthMapper()
        self.threshold = threshold

    def get_optimized_depth_map(self, image: np.ndarray) -> np.ndarray:
        # 1. Generate Near-Field Map (V2)
        self.depth_mapper.model = "depth-anything/Depth-Anything-V2-Small-hf"
        depth_v2 = np.array(self.depth_mapper.get_depth_map(image))
        if len(depth_v2.shape) == 3:
            depth_v2 = cv2.cvtColor(depth_v2, cv2.COLOR_RGB2GRAY)

        # 2. Generate Far-Field Map (Lihe)
        self.depth_mapper.model = "LiheYoung/depth-anything-small-hf"
        depth_lihe = np.array(self.depth_mapper.get_depth_map(image))
        if len(depth_lihe.shape) == 3:
            depth_lihe = cv2.cvtColor(depth_lihe, cv2.COLOR_RGB2GRAY)

        # 3. Soft blend (alpha compositing):
        # - depth_v2 contributes more where its normalized confidence is high.
        # - depth_lihe contributes more where depth_v2 is weaker.
        # This avoids hard seams between near-field and far-field behaviors.
        depth_v2_norm = cv2.normalize(depth_v2, None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)
        depth_lihe_norm = cv2.normalize(depth_lihe, None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)
        
        alpha = depth_v2_norm / 255.0
        optimized_depth = (depth_v2_norm * alpha) + (depth_lihe_norm * (1.0 - alpha))
        
        return optimized_depth.astype(np.uint8)