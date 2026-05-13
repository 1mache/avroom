from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image

from .reconstruction_3d_strategy import OutputMode, Reconstruction3DStrategy
from .reconstruction_quality import ReconstructionQuality
from .strategies.openlrm_reconstruction_strategy import OpenLrmReconstructionStrategy
from .strategies.trellis_reconstruction_strategy import TrellisReconstructionStrategy
from .strategies.vfusion3d_reconstruction_strategy import Vfusion3dReconstructionStrategy
from .strategies.triposr_reconstruction_strategy import TriposrReconstructionStrategy

logger = logging.getLogger(__name__)


class Reconstruction3DFacade:
    """Public entry point for image-to-3D reconstruction.

    Holds exactly one :class:`Reconstruction3DStrategy`. The default backend is
    OpenLRM v1.0 (``zxhezexin/openlrm-small-obj-1.0``, local PyTorch). Pass
    :class:`TrellisReconstructionStrategy` (or any other concrete strategy) at
    construction to swap backends.
    """

    def __init__(self, strategy: Reconstruction3DStrategy | None = None) -> None:
        self._strategy: Reconstruction3DStrategy = strategy or TrellisReconstructionStrategy()
        self._fallback_strategy: Reconstruction3DStrategy = TriposrReconstructionStrategy()
        logger.info(
            f"Reconstruction3DFacade ready (strategy={type(self._strategy).__name__}, "
            f"fallback={type(self._fallback_strategy).__name__})"
        )

    @property
    def strategy(self) -> Reconstruction3DStrategy:
        return self._strategy

    def generate(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        quality: ReconstructionQuality = ReconstructionQuality.HIGH,
        output: OutputMode = "bytes",
        output_path: Path | None = None,
        seed: int = 0,
    ) -> bytes | Path | BinaryIO:
        """Generate a GLB 3D model from ``image`` via the active strategy.

        If the primary strategy raises, the fallback strategy is tried with
        identical arguments. If the fallback also raises, the original
        exception from the primary strategy is re-raised.
        """
        try:
            return self._strategy.generate(
                image,
                quality=quality,
                output=output,
                output_path=output_path,
                seed=seed,
            )
        except Exception as main_exc:
            logger.warning(
                "Primary strategy %s failed (%s); trying fallback %s.",
                type(self._strategy).__name__,
                main_exc,
                type(self._fallback_strategy).__name__,
            )
            try:
                return self._fallback_strategy.generate(
                    image,
                    quality=quality,
                    output=output,
                    output_path=output_path,
                    seed=seed,
                )
            except Exception:
                raise main_exc
