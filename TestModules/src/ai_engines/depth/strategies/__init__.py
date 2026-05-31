from __future__ import annotations

from .depth_anything_mapping_strategy import DepthAnythingMappingStrategy
from .enhanced_edge_depth_mapping_strategy import EnhancedEdgeDepthMappingStrategy
from .near_far_blended_depth_mapping_strategy import NearFarBlendedDepthMappingStrategy

__all__ = [
    "DepthAnythingMappingStrategy",
    "EnhancedEdgeDepthMappingStrategy",
    "NearFarBlendedDepthMappingStrategy",
]
