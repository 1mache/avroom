from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import cv2
import numpy as np
from PIL import Image

from ..utils.debug_image_saver import DebugImageSaver

logger = logging.getLogger(__name__)

_DEBUG_FOLDER = "outputs/auto_mask_pick"

_GOOD_LABEL = "a complete unobstructed piece of furniture or household object"
_BAD_LABEL = "a partial cut, wall, floor, blob, or obstructed object"

DEFAULT_THRESHOLD = 0.6
MIN_AREA_FRACTION = 0.003
MAX_AREA_FRACTION = 0.70
_GRAY = 128


class BinaryProbScorer(Protocol):
    """Minimal CLIP scoring surface used by :func:`select_best_cutout`."""

    def binary_prob(self, pil_image: Image.Image, positive: str, negative: str) -> float:
        """Return P(positive) from a 2-label softmax."""


@dataclass(frozen=True)
class CutoutSelectionResult:
    """Outcome of ranking BGRA cutout candidates for one click.

    ``scores`` is one ``P(good)`` per input cutout. Pre-filtered candidates
    (click miss or area out of range) are recorded as ``0.0``.
    """

    winner_index: int | None
    scores: tuple[float, ...]


def select_best_cutout(
    cutouts_bgra: Sequence[np.ndarray],
    *,
    click_xy: tuple[int, int],
    scorer: BinaryProbScorer,
    threshold: float = DEFAULT_THRESHOLD,
) -> CutoutSelectionResult:
    """Pick the best complete-object cutout for ``click_xy``, or none.

    Pre-filters masks that miss the click or cover too little / too much of
    the image, then scores remaining crops with CLIP ``binary_prob``. Winner
    is the highest ``P(good)`` at or above ``threshold``.
    """
    scores: list[float] = []
    reasons: list[str] = []
    clip_crops_bgr: list[np.ndarray | None] = []
    best_index: int | None = None
    best_score = -1.0

    for index, cutout in enumerate(cutouts_bgra):
        reason = _prefilter_reason(cutout, click_xy)
        if reason is not None:
            scores.append(0.0)
            reasons.append(reason)
            clip_crops_bgr.append(None)
            continue

        crop = _crop_on_gray(cutout)
        if crop is None:
            scores.append(0.0)
            reasons.append("empty_crop")
            clip_crops_bgr.append(None)
            continue

        good_p = scorer.binary_prob(crop, _GOOD_LABEL, _BAD_LABEL)
        scores.append(good_p)
        reasons.append("scored")
        clip_crops_bgr.append(_pil_rgb_to_bgr(crop))
        if good_p >= threshold and good_p > best_score:
            best_score = good_p
            best_index = index

    if best_index is not None:
        reasons[best_index] = "winner"

    logger.info(
        "Cutout selection finished: winner=%s scores=%s threshold=%.2f",
        best_index,
        tuple(round(score, 3) for score in scores),
        threshold,
    )
    result = CutoutSelectionResult(winner_index=best_index, scores=tuple(scores))
    _save_auto_mask_debug(
        cutouts_bgra,
        click_xy=click_xy,
        result=result,
        threshold=threshold,
        reasons=tuple(reasons),
        clip_crops_bgr=clip_crops_bgr,
    )
    return result


def _prefilter_reason(cutout_bgra: np.ndarray, click_xy: tuple[int, int]) -> str | None:
    """Return a reject reason, or None if the cutout may be scored."""
    if cutout_bgra.ndim != 3 or cutout_bgra.shape[2] < 4:
        return "invalid_cutout"

    height, width = cutout_bgra.shape[:2]
    click_x, click_y = click_xy
    if click_x < 0 or click_y < 0 or click_x >= width or click_y >= height:
        return "click_miss"
    if cutout_bgra[click_y, click_x, 3] == 0:
        return "click_miss"

    alpha = cutout_bgra[:, :, 3] > 0
    area_fraction = float(np.count_nonzero(alpha)) / float(height * width)
    if area_fraction < MIN_AREA_FRACTION:
        return "area_too_small"
    if area_fraction > MAX_AREA_FRACTION:
        return "area_too_large"
    return None


def _crop_on_gray(cutout_bgra: np.ndarray) -> Image.Image | None:
    alpha = cutout_bgra[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not rows.any() or not cols.any():
        return None

    y0, y1 = np.where(rows)[0][[0, -1]]
    x0, x1 = np.where(cols)[0][[0, -1]]
    crop = cutout_bgra[y0 : y1 + 1, x0 : x1 + 1]
    rgb = cv2.cvtColor(crop[:, :, :3], cv2.COLOR_BGR2RGB)
    alpha_f = crop[:, :, 3].astype(np.float32) / 255.0
    gray = np.full_like(rgb, _GRAY, dtype=np.float32)
    blended = (
        rgb.astype(np.float32) * alpha_f[..., None] + gray * (1.0 - alpha_f[..., None])
    ).astype(np.uint8)
    return Image.fromarray(blended)


def _pil_rgb_to_bgr(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _cutout_preview_bgr(cutout_bgra: np.ndarray, click_xy: tuple[int, int]) -> np.ndarray:
    bgr = cutout_bgra[:, :, :3].copy()
    visible = cutout_bgra[:, :, 3] > 0
    bgr[~visible] = 0
    cv2.circle(bgr, click_xy, 6, (0, 0, 255), 2)
    return bgr


def _save_auto_mask_debug(
    cutouts_bgra: Sequence[np.ndarray],
    *,
    click_xy: tuple[int, int],
    result: CutoutSelectionResult,
    threshold: float,
    reasons: tuple[str, ...],
    clip_crops_bgr: Sequence[np.ndarray | None],
) -> None:
    """Write candidates, CLIP crops, winner, and score JSON under outputs/auto_mask_pick."""
    saver = DebugImageSaver(output_folder_name=_DEBUG_FOLDER)
    output_dir = Path(saver.output_dir)
    for stale in output_dir.iterdir():
        if stale.is_file():
            stale.unlink()

    candidates_meta: list[dict[str, float | int | str]] = []
    for index, cutout in enumerate(cutouts_bgra):
        score = result.scores[index] if index < len(result.scores) else 0.0
        reason = reasons[index] if index < len(reasons) else "unknown"
        saver.save(f"{index:02d}_cutout", cutout)
        if cutout.ndim == 3 and cutout.shape[2] >= 4:
            saver.save(f"{index:02d}_alpha", cutout[:, :, 3])
            saver.save(f"{index:02d}_preview", _cutout_preview_bgr(cutout, click_xy))
        crop_bgr = clip_crops_bgr[index] if index < len(clip_crops_bgr) else None
        if crop_bgr is not None:
            saver.save(f"{index:02d}_clip_crop", crop_bgr)
        candidates_meta.append({"index": index, "score": round(float(score), 4), "reason": reason})

    if result.winner_index is not None and 0 <= result.winner_index < len(cutouts_bgra):
        saver.save("winner", cutouts_bgra[result.winner_index])

    summary = {
        "click_xy": [click_xy[0], click_xy[1]],
        "threshold": threshold,
        "winner_index": result.winner_index,
        "candidates": candidates_meta,
    }
    summary_path = output_dir / "selection.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Auto mask pick debug saved: %s", output_dir)
