from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class InpaintResult:
    """Outcome of :meth:`ImageInpaintingStrategy.inpaint`.

    ``compose_dilate_pixels`` and ``final_inpaint_mask`` are populated by
    :class:`HybridInpaintingStrategy` when its verifier grows the inpaint hole
    on a retry -- the caller (:class:`BackgroundInpainter`) widens its
    paste-back mask to match, so the newly-inpainted ring isn't discarded.
    Strategies that never dilate (LaMa, plain SD) return the defaults, which
    are no-ops for the caller.
    """

    image: np.ndarray
    compose_dilate_pixels: int = 0
    final_inpaint_mask: np.ndarray | None = None
    verification_ok: bool | None = None
