from __future__ import annotations

import functools
import logging
from typing import Any

import numpy as np
from PIL import Image

from ..depth_mapping_strategy import DepthMappingStrategy

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=4)
def _load_depth_pipeline(model_name: str, task: str) -> Any:
    """Load (and cache) a transformers depth-estimation pipeline.

    Cached per (model_name, task) so that switching between near and far
    Depth Anything variants in :class:`NearFarBlendedDepthMappingStrategy`
    only pays the load cost once per process.
    """
    # Imported lazily so importing this module does not pull torch + transformers.
    from transformers import pipeline

    logger.info(f"Loading depth pipeline: model={model_name} task={task}")
    return pipeline(task=task, model=model_name)


class DepthAnythingMappingStrategy(DepthMappingStrategy):
    """Depth-mapping strategy backed by a Depth Anything family model.

    The class is generic over the model name (any depth-estimation checkpoint
    discoverable by ``transformers.pipeline`` works), but in production we use
    Depth Anything V2 / LiheYoung Depth Anything Small variants - hence the
    name. Source library is an implementation detail and intentionally not in
    the class name.
    """

    DEFAULT_MODEL: str = "LiheYoung/depth-anything-small-hf"
    DEFAULT_TASK: str = "depth-estimation"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        task: str = DEFAULT_TASK,
    ) -> None:
        self._model_name = model_name
        self._task = task
        logger.info(
            f"DepthAnythingMappingStrategy created: model={model_name} task={task}"
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    def map_depth(self, image: np.ndarray) -> np.ndarray:
        pipe = _load_depth_pipeline(self._model_name, self._task)

        if isinstance(image, np.ndarray):
            pil_image = Image.fromarray(image.astype("uint8"))
        else:
            pil_image = image

        result = pipe(pil_image)
        depth_image = result["depth"]
        return np.array(depth_image)
