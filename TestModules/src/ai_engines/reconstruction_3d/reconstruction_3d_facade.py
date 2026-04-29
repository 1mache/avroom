from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image

from .reconstruction_3d_strategy import OutputMode, Reconstruction3DStrategy
from .reconstruction_quality import ReconstructionQuality
from .strategies.trellis_reconstruction_strategy import TrellisReconstructionStrategy

logger = logging.getLogger(__name__)


class Reconstruction3DFacade:
    """Public entry point for image-to-3D reconstruction.

    Holds exactly one :class:`Reconstruction3DStrategy`. Default backend is
    Trellis 2 via Hugging Face Space; pass any other concrete strategy at
    construction to swap (e.g. a future Hunyuan3D strategy).
    """

    def __init__(self, strategy: Reconstruction3DStrategy | None = None) -> None:
        self._strategy: Reconstruction3DStrategy = strategy or TrellisReconstructionStrategy()
        logger.info(
            f"Reconstruction3DFacade ready (strategy={type(self._strategy).__name__})"
        )

    @property
    def strategy(self) -> Reconstruction3DStrategy:
        return self._strategy

    def generate(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        quality: ReconstructionQuality = ReconstructionQuality.FAST,
        output: OutputMode = "bytes",
        output_path: Path | None = None,
        seed: int = 0,
    ) -> bytes | Path | BinaryIO:
        """Generate a GLB 3D model from ``image`` via the active strategy."""
        return self._strategy.generate(
            image,
            quality=quality,
            output=output,
            output_path=output_path,
            seed=seed,
        )
