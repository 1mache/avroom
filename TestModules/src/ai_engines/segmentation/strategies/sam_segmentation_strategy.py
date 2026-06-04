from __future__ import annotations

import functools
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from ....utils.debug_image_saver import DebugImageSaver
from ....utils.mask_refiner import MaskRefiner
from ..image_segmentation_strategy import ImageSegmentationStrategy

logger = logging.getLogger(__name__)


SAM_CHECKPOINT_NAME = "sam_vit_b_01ec64.pth"
SAM_DEFAULT_URL = f"https://dl.fbaipublicfiles.com/segment_anything/{SAM_CHECKPOINT_NAME}"


def _get_default_checkpoint_path() -> Path:
    # ai_engines/segmentation/strategies/<this file> -> 4 levels up to TestModules/.
    current_dir = Path(__file__).resolve().parent
    return (current_dir / ".." / ".." / ".." / ".." / "checkpoints" / SAM_CHECKPOINT_NAME).resolve()


def _resolve_checkpoint_path() -> Path:
    """Resolve SAM checkpoint location with the legacy 3-step lookup.

    1. Honor ``SAM_CHECKPOINT_PATH`` env var if set (must exist).
    2. Use ``TestModules/checkpoints/<name>`` if present.
    3. Optionally auto-download from ``SAM_CHECKPOINT_URL`` (default Meta CDN)
       when ``SAM_AUTO_DOWNLOAD`` is truthy (default ``"1"``).
    """
    env_path = os.getenv("SAM_CHECKPOINT_PATH")
    if env_path:
        explicit = Path(env_path).expanduser().resolve()
        if explicit.exists():
            return explicit
        raise FileNotFoundError(
            f"SAM_CHECKPOINT_PATH points to missing file: {explicit}"
        )

    checkpoint_path = _get_default_checkpoint_path()
    if checkpoint_path.exists():
        return checkpoint_path

    auto_download = os.getenv("SAM_AUTO_DOWNLOAD", "1").strip().lower() not in {"0", "false", "no"}
    if not auto_download:
        raise FileNotFoundError(
            f"Missing SAM checkpoint: {checkpoint_path}. "
            f"Set SAM_CHECKPOINT_PATH or enable SAM_AUTO_DOWNLOAD=1."
        )

    checkpoint_url = os.getenv("SAM_CHECKPOINT_URL", SAM_DEFAULT_URL)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading SAM checkpoint from {checkpoint_url} -> {checkpoint_path}")
    urllib.request.urlretrieve(checkpoint_url, checkpoint_path)
    logger.info("SAM checkpoint download complete")
    return checkpoint_path


@functools.lru_cache(maxsize=1)
def _load_sam_predictor(checkpoint_path: str, model_type: str, device: str) -> Any:
    """Load and cache a single SamPredictor instance per process.

    Replaces the legacy ``SamFacadeSingleton``: the strategy class itself is a
    plain object (instantiating multiple is harmless), but the ~370 MB SAM
    weights are loaded only once.
    """
    from segment_anything import SamPredictor, sam_model_registry

    logger.info(f"Loading SAM ({model_type}) on {device} from {checkpoint_path}")
    sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
    sam.to(device=device)
    return SamPredictor(sam)


class SamSegmentationStrategy(ImageSegmentationStrategy):
    """Segment Anything (Meta) point-prompted segmentation strategy.

    The SAM weights are loaded lazily and reused across all instances thanks
    to the module-level ``functools.lru_cache``. The strategy itself only
    holds plain config (paths, device choice, mask-refinement helper).
    """

    DEFAULT_MODEL_TYPE: str = "vit_b"

    def __init__(
        self,
        checkpoint_path: str | Path | None = None,
        model_type: str = DEFAULT_MODEL_TYPE,
        device: str | None = None,
        mask_refiner: MaskRefiner | None = None,
    ) -> None:
        resolved_path = Path(checkpoint_path) if checkpoint_path else _resolve_checkpoint_path()
        self._checkpoint_path: str = str(resolved_path)
        self._model_type = model_type
        self._device = device or self._auto_device()
        self._mask_refiner: MaskRefiner = mask_refiner or MaskRefiner()
        logger.info(
            f"SamSegmentationStrategy created (model={model_type}, device={self._device})"
        )

    @staticmethod
    def _auto_device() -> str:
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ModuleNotFoundError:
            return "cpu"

    @property
    def _predictor(self) -> Any:
        return _load_sam_predictor(self._checkpoint_path, self._model_type, self._device)

    def _run_sam_predict(
        self,
        image: np.ndarray,
        x: int,
        y: int,
        *,
        save_debug: bool = True,
    ) -> tuple[Any, DebugImageSaver]:
        """Run SAM multimask prediction and optionally save per-candidate debug images.

        Args:
            save_debug: When ``True`` (default), writes ``mask_0`` … ``mask_N``
                to the debug output directory. Pass ``False`` when the caller
                (e.g. ``predict_all_masks`` via ``ObjectSegmentor``) will save
                its own labeled artifacts, to avoid unlabeled duplicates that
                get silently overwritten on the second pass.

        Returns the raw ``masks`` array alongside the shared ``DebugImageSaver``
        instance so callers can append further saves to the same directory.
        """
        predictor = self._predictor
        predictor.set_image(image)

        input_point = np.array([[x, y]])
        input_label = np.array([1])  # 1 = foreground

        masks, _scores, _logits = predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=True,
        )

        image_saver = DebugImageSaver()
        if save_debug:
            for i, mask in enumerate(masks):
                image_saver.save(f"mask_{i}.png", mask)

        return masks, image_saver

    def predict_mask(
        self,
        image: np.ndarray,
        x: int,
        y: int,
        *,
        expand_pixels: int = 0,
        use_broad_mask: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        masks, image_saver = self._run_sam_predict(image, x, y)

        # Index 1 is SAM's "tight" candidate - good for flat objects (TVs,
        # windows). use_broad_mask is accepted for interface symmetry; the
        # legacy code never actually switched indices on it, so we don't either.
        best_mask = masks[1]

        original_mask = best_mask
        if expand_pixels > 0:
            expanded_mask = self._mask_refiner.dilate_mask(best_mask, pixels=expand_pixels)
            image_saver.save("dilated_mask.png", expanded_mask)
        else:
            expanded_mask = best_mask.copy()

        image_saver.save("best_mask.png", expanded_mask)
        return expanded_mask, original_mask

    def predict_all_masks(
        self,
        image: np.ndarray,
        x: int,
        y: int,
        *,
        expand_pixels: int = 0,
        use_broad_mask: bool = False,
    ) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
        """Return one ``(expanded_mask, original_mask)`` pair per SAM candidate.

        SAM's ``multimask_output=True`` mode yields three candidates (indices
        0, 1, 2 — roughly small, tight, broad). This method returns all three
        so callers can pick or compare them without running SAM multiple times.
        Each candidate is independently dilated by ``expand_pixels`` when
        non-zero; otherwise a distinct copy is returned.
        """
        # ObjectSegmentor saves labeled per-candidate artifacts for every pair
        # it receives, so we skip the raw unlabeled saves here to avoid writing
        # files that would be silently overwritten by the second (image) pass.
        masks, _image_saver = self._run_sam_predict(image, x, y, save_debug=False)

        candidate_pairs: list[tuple[np.ndarray, np.ndarray]] = []
        for i, raw_mask in enumerate(masks):
            original_mask = raw_mask
            if expand_pixels > 0:
                expanded_mask = self._mask_refiner.dilate_mask(raw_mask, pixels=expand_pixels)
            else:
                expanded_mask = raw_mask.copy()
            candidate_pairs.append((expanded_mask, original_mask))

        return tuple(candidate_pairs)
