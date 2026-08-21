from __future__ import annotations

"""Run Metric3D normal mapping on raw image bytes for inference jobs."""

import logging

import cv2
import numpy as np

from core.avroom_package import load_avroom_attr
from core.depth_cache import memory_image_key

logger = logging.getLogger(__name__)

_NORMAL_MAPPING_MODULE = "avroom_object_removal.ai_engines.normal_mapping"


def map_normals_image_bytes(image_bytes: bytes) -> np.ndarray:
    """Decode ``image_bytes`` and return camera-frame unit normals (float32 HxWx3)."""
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("Image bytes are not a valid image for normal mapping.")

    facade = load_avroom_attr("NormalMappingFacade", _NORMAL_MAPPING_MODULE)()
    image_key = memory_image_key(image_bytes)
    logger.info("Normal mapping start: key=%s shape=%s", image_key[:24], decoded.shape)
    normals = facade.map_normals(decoded)
    logger.info(
        "Normal mapping success: shape=%s dtype=%s",
        normals.shape,
        normals.dtype,
    )
    return normals
