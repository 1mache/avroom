from __future__ import annotations

from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
from PIL import Image

from .reconstruction_quality import ReconstructionQuality

OutputMode = Literal["bytes", "path", "file"]


class Reconstruction3DStrategy(ABC):
    """Abstract Strategy for image-to-3D reconstruction.

    Implementations take a single segmented image (anything :func:`to_pil_rgba`
    can normalize) and return a GLB asset in the requested form: raw bytes,
    a filesystem path, or an ``io.BytesIO``.

    Concrete strategies live under :mod:`avroom_object_removal.ai_engines.reconstruction_3d.strategies`.
    """

    @abstractmethod
    def generate(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        quality: ReconstructionQuality = ReconstructionQuality.FAST,
        output: OutputMode = "bytes",
        output_path: Path | None = None,
        seed: int = 0,
    ) -> bytes | Path | BinaryIO:
        """Generate a GLB 3D model from ``image``.

        See concrete strategies for accepted input types and behavior of
        ``output``. ``BytesIO`` is returned for ``output="file"``.
        """
        raise NotImplementedError
